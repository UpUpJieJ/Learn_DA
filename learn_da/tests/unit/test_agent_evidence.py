"""阶段 3 Task 1：服务端练习证据解析器测试。

覆盖计划要求：
- 伪造 attemptId / lesson slug / 验证状态不能影响其他 visitor 的反馈；
- 代码成功与验证通过分别进入不同 evidence 分支；
- unverifiable / runner_unavailable 不进入"代码错误"提示；
- 无 Attempt 时不构造虚假失败上下文；
- 自动上下文不包含历史 Attempt 的 code 字段；
- 五态推导正确。
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.agent.evidence import (
    AgentEvidenceResolver,
    AgentLearningEvidence,
    derive_state,
)
from app.practice.models import ExerciseAttempt


# =====================================================
# 辅助：构造 Attempt 与 mock 依赖
# =====================================================


def make_attempt(
    *,
    id=1,
    visitor_id="visitor-A",
    lesson_slug="polars-basics",
    exercise_id="ex-001",
    execution_status="success",
    verification_status="passed",
    failure_reason=None,
    stdout="ok",
    stderr=None,
    duration_ms=120,
    created_time=None,
    code="SECRET_CODE_SHOULD_NOT_LEAK",
) -> ExerciseAttempt:
    """构造一个内存 ExerciseAttempt（不落库）。"""
    a = ExerciseAttempt()
    a.id = id
    a.visitor_id = visitor_id
    a.request_id = f"req-{id}"
    a.lesson_slug = lesson_slug
    a.exercise_id = exercise_id
    a.execution_id = None
    a.source = "playground"
    a.language = "python"
    a.code = code
    a.execution_status = execution_status
    a.verification_status = verification_status
    a.failure_reason = failure_reason
    a.stdout = stdout
    a.stderr = stderr
    a.duration_ms = duration_ms
    a.created_time = created_time or datetime(2026, 7, 31, 10, 0, 0, tzinfo=timezone.utc)
    a.is_deleted = False
    return a


def make_resolver(
    *,
    get_by_id_return=None,
    get_latest_by_lesson_return=None,
    lesson_progress_status=None,
) -> AgentEvidenceResolver:
    """构造带 mock 依赖的 resolver。"""
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=get_by_id_return)
    repo.get_latest_by_lesson = AsyncMock(return_value=get_latest_by_lesson_return)

    learner_state = AsyncMock()
    progress = MagicMock()
    progress.status = lesson_progress_status
    learner_state.get_lesson_progress = AsyncMock(return_value=progress)

    return AgentEvidenceResolver(
        practice_repo=repo, learner_state_service=learner_state
    )


# =====================================================
# 五态推导（derive_state）
# =====================================================


class TestDeriveState:
    def test_execution_failed(self):
        assert derive_state("error", "not_run") == "execution_failed"
        assert derive_state("timeout", "not_run") == "execution_failed"
        assert derive_state("rejected", "not_run") == "execution_failed"

    def test_unavailable_is_unverifiable(self):
        assert derive_state("unavailable", "not_run") == "unverifiable"

    def test_verification_unverifiable(self):
        assert derive_state("success", "unverifiable") == "unverifiable"

    def test_verification_failed(self):
        assert derive_state("success", "failed") == "verification_failed"
        assert derive_state("completed", "failed") == "verification_failed"

    def test_passed(self):
        assert derive_state("success", "passed") == "passed_unconfirmed"
        assert derive_state("completed", "passed") == "passed_unconfirmed"

    def test_not_run_success_is_unverifiable(self):
        # 执行成功但未跑断言 -> 无法判定目标是否达成
        assert derive_state("success", "not_run") == "unverifiable"

    def test_no_evidence(self):
        assert derive_state(None, None) == "no_evidence"


# =====================================================
# 解析顺序：指定 Attempt -> 课程最近 -> 无 Attempt
# =====================================================


class TestResolutionOrder:
    @pytest.mark.asyncio
    async def test_specified_attempt_used_first(self):
        """提供 attemptId 时优先使用该 attempt。"""
        specified = make_attempt(id=42, verification_status="failed")
        latest = make_attempt(id=10, verification_status="passed")
        resolver = make_resolver(
            get_by_id_return=specified,
            get_latest_by_lesson_return=latest,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A",
            lesson_slug="polars-basics",
            attempt_id=42,
        )

        assert evidence.attempt_id == 42
        assert evidence.state == "verification_failed"
        # 必须用 visitor_id 过滤
        resolver.practice_repo.get_by_id.assert_called_once_with(
            42, "visitor-A"
        )
        # 指定 attempt 命中后不应回退查 latest
        resolver.practice_repo.get_latest_by_lesson.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_to_latest_by_lesson(self):
        """无 attemptId 时回退到课程最近 Attempt。"""
        latest = make_attempt(id=10, verification_status="passed")
        resolver = make_resolver(
            get_by_id_return=None,
            get_latest_by_lesson_return=latest,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A",
            lesson_slug="polars-basics",
            attempt_id=None,
        )

        assert evidence.attempt_id == 10
        assert evidence.state == "passed_unconfirmed"
        resolver.practice_repo.get_latest_by_lesson.assert_called_once_with(
            "visitor-A", "polars-basics"
        )

    @pytest.mark.asyncio
    async def test_no_attempt_yields_no_evidence(self):
        """无任何 Attempt 时返回 no_evidence，不构造虚假失败上下文。"""
        resolver = make_resolver(
            get_by_id_return=None,
            get_latest_by_lesson_return=None,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A",
            lesson_slug="polars-basics",
            attempt_id=None,
        )

        assert evidence.state == "no_evidence"
        assert evidence.attempt_id is None
        assert evidence.execution_status is None
        assert evidence.verification_status is None
        assert evidence.failure_reason is None
        assert evidence.stdout_summary is None
        assert evidence.stderr_summary is None
        assert evidence.lesson_slug is None

    @pytest.mark.asyncio
    async def test_no_lesson_slug_skips_latest_lookup(self):
        """无 lesson_slug 时不查课程最近 Attempt。"""
        resolver = make_resolver(
            get_by_id_return=None,
            get_latest_by_lesson_return=None,
            lesson_progress_status=None,
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A",
            lesson_slug=None,
            attempt_id=None,
        )

        assert evidence.state == "no_evidence"
        resolver.practice_repo.get_latest_by_lesson.assert_not_called()


# =====================================================
# 归属隔离：伪造 attemptId / lesson 不能读取他人证据
# =====================================================


class TestOwnershipIsolation:
    @pytest.mark.asyncio
    async def test_forged_attempt_id_returns_no_evidence(self):
        """伪造的 attemptId（属于其他 visitor）查不到，返回 no_evidence。"""
        # get_by_id 按 visitor 过滤，其他 visitor 的 attempt 返回 None
        resolver = make_resolver(
            get_by_id_return=None,  # 其他 visitor 的 attempt 查不到
            get_latest_by_lesson_return=None,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="attacker",
            lesson_slug="polars-basics",
            attempt_id=999,  # 属于 visitor-A
        )

        assert evidence.state == "no_evidence"
        # 校验确实用了 attacker 的 visitor_id
        resolver.practice_repo.get_by_id.assert_called_once_with(999, "attacker")

    @pytest.mark.asyncio
    async def test_attempt_lesson_mismatch_is_rejected(self):
        """attempt 与客户端声明的 lesson 不一致时不采信。"""
        # attempt 属于 visitor-A，但 lesson 是别的
        mismatch_attempt = make_attempt(
            id=42, lesson_slug="duckdb-basics", verification_status="passed"
        )
        resolver = make_resolver(
            get_by_id_return=mismatch_attempt,
            get_latest_by_lesson_return=None,  # 声明的 lesson 无最近 attempt
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A",
            lesson_slug="polars-basics",  # 声明 polars，但 attempt 属于 duckdb
            attempt_id=42,
        )

        # 不一致 -> 丢弃该 attempt，回退查 polars-basics 最近 -> 无 -> no_evidence
        assert evidence.state == "no_evidence"
        assert evidence.attempt_id is None
        resolver.practice_repo.get_latest_by_lesson.assert_not_called()


# =====================================================
# 五态证据构造（含截断与字段隔离）
# =====================================================


class TestEvidenceConstruction:
    @pytest.mark.asyncio
    async def test_execution_failed_evidence(self):
        attempt = make_attempt(
            execution_status="error",
            verification_status="not_run",
            failure_reason="SyntaxError: invalid syntax",
            stderr="Traceback (most recent call last):\n  ...",
        )
        resolver = make_resolver(
            get_latest_by_lesson_return=attempt,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        assert evidence.state == "execution_failed"
        assert evidence.execution_status == "error"
        assert evidence.failure_reason == "SyntaxError: invalid syntax"
        assert evidence.stderr_summary is not None

    @pytest.mark.asyncio
    async def test_verification_failed_evidence(self):
        attempt = make_attempt(
            execution_status="success",
            verification_status="failed",
            failure_reason="stdout_mismatch",
            stdout="expected 5, got 3",
        )
        resolver = make_resolver(
            get_latest_by_lesson_return=attempt,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        assert evidence.state == "verification_failed"
        assert evidence.verification_status == "failed"
        assert evidence.stdout_summary == "expected 5, got 3"

    @pytest.mark.asyncio
    async def test_passed_unconfirmed_evidence(self):
        attempt = make_attempt(
            execution_status="success",
            verification_status="passed",
        )
        resolver = make_resolver(
            get_latest_by_lesson_return=attempt,
            lesson_progress_status="started",  # 课程未完成
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        assert evidence.state == "passed_unconfirmed"
        assert evidence.lesson_completed is False

    @pytest.mark.asyncio
    async def test_passed_with_lesson_completed(self):
        """练习通过且课程已完成：仍为 passed_unconfirmed，但 lesson_completed=True。"""
        attempt = make_attempt(
            execution_status="success",
            verification_status="passed",
        )
        resolver = make_resolver(
            get_latest_by_lesson_return=attempt,
            lesson_progress_status="completed",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        assert evidence.state == "passed_unconfirmed"
        assert evidence.lesson_completed is True

    @pytest.mark.asyncio
    async def test_unverifiable_runner_unavailable(self):
        """Runner 不可用 -> unverifiable，不进入 execution_failed。"""
        attempt = make_attempt(
            execution_status="unavailable",
            verification_status="not_run",
            failure_reason="runner_unavailable",
        )
        resolver = make_resolver(
            get_latest_by_lesson_return=attempt,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        assert evidence.state == "unverifiable"
        assert evidence.execution_status == "unavailable"

    @pytest.mark.asyncio
    async def test_unverifiable_verification_inconclusive(self):
        attempt = make_attempt(
            execution_status="success",
            verification_status="unverifiable",
        )
        resolver = make_resolver(
            get_latest_by_lesson_return=attempt,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        assert evidence.state == "unverifiable"

    @pytest.mark.asyncio
    async def test_code_field_never_in_evidence(self):
        """证据不包含历史 Attempt 的 code 字段。"""
        attempt = make_attempt(code="df = pl.read_csv('secret.csv')")
        resolver = make_resolver(
            get_latest_by_lesson_return=attempt,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        # AgentLearningEvidence 没有 code 字段
        assert not hasattr(evidence, "code")
        # 序列化也不应出现 code
        dumped = evidence.model_dump()
        assert "code" not in dumped
        assert "secret.csv" not in str(dumped)

    @pytest.mark.asyncio
    async def test_stdout_stderr_truncated(self):
        """超长 stdout/stderr 被截断。"""
        long_stdout = "x" * 2000
        long_stderr = "y" * 2000
        attempt = make_attempt(
            execution_status="error",
            stdout=long_stdout,
            stderr=long_stderr,
        )
        resolver = make_resolver(
            get_latest_by_lesson_return=attempt,
            lesson_progress_status="started",
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        assert len(evidence.stdout_summary) <= 600  # 500 + 截断标记
        assert "截断" in evidence.stdout_summary
        assert len(evidence.stderr_summary) <= 600


# =====================================================
# learner_state 读取容错
# =====================================================


class TestLearnerStateResilience:
    @pytest.mark.asyncio
    async def test_learner_state_exception_treated_as_not_completed(self):
        """learner_state 读取失败时按未完成处理，不阻断证据解析。"""
        attempt = make_attempt(verification_status="passed")
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)
        repo.get_latest_by_lesson = AsyncMock(return_value=attempt)

        learner_state = AsyncMock()
        learner_state.get_lesson_progress = AsyncMock(side_effect=RuntimeError("db down"))

        resolver = AgentEvidenceResolver(
            practice_repo=repo, learner_state_service=learner_state
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        assert evidence.state == "passed_unconfirmed"
        assert evidence.lesson_completed is False

    @pytest.mark.asyncio
    async def test_no_learner_service_treated_as_not_completed(self):
        """未注入 learner_state_service 时按未完成处理。"""
        attempt = make_attempt(verification_status="passed")
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)
        repo.get_latest_by_lesson = AsyncMock(return_value=attempt)

        resolver = AgentEvidenceResolver(
            practice_repo=repo, learner_state_service=None
        )

        evidence = await resolver.resolve(
            visitor_id="visitor-A", lesson_slug="polars-basics"
        )

        assert evidence.lesson_completed is False
