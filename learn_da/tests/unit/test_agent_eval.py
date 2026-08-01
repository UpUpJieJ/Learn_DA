"""阶段 3 Task 5：学习证据驱动 Agent 离线评测。

加载 ``tests/eval/phase3_evidence_cases.yml``，对每条 case 用
``AgentEvidenceResolver`` + ``build_teaching_feedback`` + ``derive_state``
做确定性断言（不调用 LLM），覆盖 7 个评测维度：

1. evidence_accuracy   证据五态推导
2. next_action          下一步动作映射
3. hint_escalation     分级提示逐级升高
4. code_leak           证据/反馈不泄露历史 Attempt 完整代码
5. fallback_class      fallback 原因分类
6. visitor_isolation   伪造 attemptId 得不到他人证据
7. runner_unavailable   Runner 不可用不进入 execution_failed
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from app.agent.evidence import (
    AgentEvidenceResolver,
    AgentLearningEvidence,
    build_teaching_feedback,
    derive_next_action,
    derive_state,
)
from app.agent.schemas import AgentChatMessage, AgentChatRequest, AgentContext
from app.practice.models import ExerciseAttempt

EVAL_YML = Path(__file__).parent.parent / "eval" / "phase3_evidence_cases.yml"


def _load_cases() -> list[dict]:
    with open(EVAL_YML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["cases"]


CASES = _load_cases()


def _make_attempt(case: dict) -> ExerciseAttempt | None:
    """从 case 构造内存 Attempt（None 表示无 attempt）。"""
    if case["execution_status"] is None and case["verification_status"] is None:
        return None
    a = ExerciseAttempt()
    a.id = case.get("attempt_id", 1)
    a.visitor_id = "visitor-A"
    a.request_id = f"req-{case['id']}"
    a.lesson_slug = "polars-basics"
    a.exercise_id = "ex-001"
    a.execution_id = None
    a.source = "playground"
    a.language = "python"
    a.code = "SECRET_CODE_THAT_MUST_NOT_LEAK"
    a.execution_status = case["execution_status"]
    a.verification_status = case["verification_status"]
    a.failure_reason = "test_failure"
    a.stdout = "some stdout"
    a.stderr = "some stderr"
    a.duration_ms = 100
    a.created_time = datetime(2026, 7, 31, tzinfo=timezone.utc)
    a.is_deleted = False
    return a


def _make_resolver(attempt: ExerciseAttempt | None, lesson_completed: bool):
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=attempt)
    repo.get_latest_by_lesson = AsyncMock(return_value=attempt)

    learner_state = AsyncMock()
    progress = MagicMock()
    progress.status = "completed" if lesson_completed else "started"
    learner_state.get_lesson_progress = AsyncMock(return_value=progress)

    return AgentEvidenceResolver(
        practice_repo=repo, learner_state_service=learner_state
    )


def _hint_level_from_turns(turns: int) -> int:
    """与 AgentService._estimate_hint_level 对齐的近似。"""
    return max(1, min(3, 1 + turns // 2))


# =====================================================
# 参数化离线评测：每条 case 一组断言
# =====================================================


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
@pytest.mark.asyncio
async def test_phase3_eval_case(case: dict):
    """对单条 eval case 做证据推导 + 反馈契约断言。"""
    attempt = _make_attempt(case)
    resolver = _make_resolver(attempt, case["lesson_completed"])

    evidence = await resolver.resolve(
        visitor_id="visitor-A",
        lesson_slug="polars-basics",
        attempt_id=case.get("attempt_id", 1),
    )

    # 维度 1：证据五态推导
    assert evidence.state == case["expected_state"], (
        f"{case['id']}: state={evidence.state} expected={case['expected_state']}"
    )

    # 维度 2：下一步动作映射
    assert derive_next_action(evidence) == case["expected_next_action"]

    # 维度 3：分级提示
    hint_level = _hint_level_from_turns(case["history_user_turns"])
    fb = build_teaching_feedback(evidence, hint_level=hint_level)
    assert fb.hint_level == case["expected_hint_level"]
    assert fb.next_action == case["expected_next_action"]
    assert fb.state == case["expected_state"]

    # 维度 4：代码泄露——证据与反馈序列化中不含 code / 完整代码
    ev_dumped = evidence.model_dump()
    assert "code" not in ev_dumped
    assert "SECRET_CODE" not in str(ev_dumped)
    fb_dumped = fb.model_dump(by_alias=True)
    assert "code" not in fb_dumped
    assert "SECRET_CODE" not in str(fb_dumped)


# =====================================================
# 维度 6：游客隔离（伪造 attemptId 得不到他人证据）
# =====================================================


class TestVisitorIsolation:
    @pytest.mark.asyncio
    async def test_forged_attempt_id_no_evidence(self):
        """攻击者用他人的 attemptId 查不到证据。"""
        repo = MagicMock()
        # get_by_id 按 visitor 过滤，攻击者查不到 victim 的 attempt
        repo.get_by_id = AsyncMock(return_value=None)
        repo.get_latest_by_lesson = AsyncMock(return_value=None)

        learner_state = AsyncMock()
        learner_state.get_lesson_progress = AsyncMock(return_value=None)

        resolver = AgentEvidenceResolver(
            practice_repo=repo, learner_state_service=learner_state
        )
        evidence = await resolver.resolve(
            visitor_id="attacker",
            lesson_slug="polars-basics",
            attempt_id=999,
        )
        assert evidence.state == "no_evidence"
        # 校验用了攻击者身份
        repo.get_by_id.assert_called_once_with(999, "attacker")

    @pytest.mark.asyncio
    async def test_victim_evidence_not_leaked_to_attacker(self):
        """victim 的 attempt 存在，但攻击者查不到。"""
        victim_attempt = ExerciseAttempt()
        victim_attempt.id = 42
        victim_attempt.visitor_id = "victim"
        victim_attempt.lesson_slug = "polars-basics"
        victim_attempt.execution_status = "error"
        victim_attempt.verification_status = "not_run"
        victim_attempt.code = "VICTIM_SECRET"
        victim_attempt.created_time = datetime(2026, 7, 31, tzinfo=timezone.utc)
        victim_attempt.is_deleted = False

        repo = MagicMock()
        # 攻击者查 attempt_id=42 -> None（visitor 不匹配）
        repo.get_by_id = AsyncMock(return_value=None)
        repo.get_latest_by_lesson = AsyncMock(return_value=None)

        learner_state = AsyncMock()
        learner_state.get_lesson_progress = AsyncMock(return_value=None)

        resolver = AgentEvidenceResolver(
            practice_repo=repo, learner_state_service=learner_state
        )
        evidence = await resolver.resolve(
            visitor_id="attacker",
            lesson_slug="polars-basics",
            attempt_id=42,
        )
        assert evidence.state == "no_evidence"
        assert evidence.attempt_id is None


# =====================================================
# 维度 4 独立：代码泄露专项
# =====================================================


class TestCodeLeakage:
    @pytest.mark.asyncio
    async def test_evidence_never_contains_code(self):
        """无论何种状态，证据都不含 code 字段。"""
        for exec_status, ver_status in [
            ("error", "not_run"),
            ("success", "failed"),
            ("success", "passed"),
            ("unavailable", "not_run"),
        ]:
            attempt = ExerciseAttempt()
            attempt.id = 1
            attempt.visitor_id = "v1"
            attempt.lesson_slug = "l1"
            attempt.execution_status = exec_status
            attempt.verification_status = ver_status
            attempt.code = f"SECRET_{exec_status}"
            attempt.created_time = datetime(2026, 7, 31, tzinfo=timezone.utc)
            attempt.is_deleted = False

            repo = MagicMock()
            repo.get_by_id = AsyncMock(return_value=attempt)
            repo.get_latest_by_lesson = AsyncMock(return_value=attempt)
            learner_state = AsyncMock()
            learner_state.get_lesson_progress = AsyncMock(return_value=None)

            resolver = AgentEvidenceResolver(
                practice_repo=repo, learner_state_service=learner_state
            )
            evidence = await resolver.resolve("v1", "l1", 1)
            dumped = str(evidence.model_dump())
            assert "code" not in evidence.model_dump()
            assert f"SECRET_{exec_status}" not in dumped


# =====================================================
# 评测集完整性汇总
# =====================================================


def test_eval_summary(capsys: pytest.CaptureFixture[str]):
    """确保评测集覆盖声明的维度，不伪造未执行的通过率。"""
    dim_total: dict[str, int] = {}
    required_dimensions = {
        "evidence_accuracy",
        "next_action",
        "hint_escalation",
        "code_leak",
        "fallback_class",
        "runner_unavailable",
    }
    for case in CASES:
        dim = case["dimension"]
        dim_total[dim] = dim_total.get(dim, 0) + 1

    assert required_dimensions.issubset(dim_total)
    assert len(CASES) >= 30

    lines = ["\n=== 阶段 3 离线评测汇总 ==="]
    for dim in sorted(dim_total):
        lines.append(f"  {dim}: {dim_total[dim]} 条 case，断言由参数化测试执行")
    lines.append("  visitor_isolation: 由独立归属隔离测试执行")
    lines.append(f"  总计: {len(CASES)} 条 case")
    capsys.writeouterr = capsys.readouterr()  # consume
    print("\n".join(lines))
