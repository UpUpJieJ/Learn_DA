"""阶段 3 Task 2：结构化教学反馈契约与分级提示测试。

覆盖计划要求：
- 五种 evidence state 均有 LLM 与 fallback 返回值测试；
- 模型给出冲突 JSON 或不当完整答案时，服务端保留权威 state 并降级；
- UI 对不同 nextAction 显示正确动作（此处验证 nextAction 派生正确）。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agent.evidence import (
    AgentLearningEvidence,
    build_teaching_feedback,
    derive_next_action,
)
from app.agent.schemas import (
    AgentChatData,
    AgentChatRequest,
    AgentContext,
    TeachingFeedback,
)


# =====================================================
# build_teaching_feedback：五态全覆盖
# =====================================================


def _evidence(state: str, **kw) -> AgentLearningEvidence:
    defaults = dict(
        state=state,
        source="workspace",
        lesson_slug="polars-groupby",
        attempt_id=42,
        attempt_no=1,
        task_id="t1",
        task_title="按区域聚合",
        verdict="passed",
        lesson_completed=False,
        evidence_time="2026-07-31 10:00:00",
    )
    defaults.update(kw)
    return AgentLearningEvidence(**defaults)


class TestBuildTeachingFeedback:
    def test_execution_failed(self):
        fb = build_teaching_feedback(
            _evidence("execution_failed", verdict="execution_failed")
        )
        assert fb.state == "execution_failed"
        assert fb.attempt_id == 42
        assert fb.next_action == "retry_exercise"
        assert fb.hint_level == 1
        assert fb.evidence_summary
        assert fb.diagnosis

    def test_verification_failed(self):
        fb = build_teaching_feedback(
            _evidence("verification_failed", verdict="assertion_failed")
        )
        assert fb.state == "verification_failed"
        assert fb.next_action == "retry_exercise"

    def test_passed_unconfirmed_not_completed(self):
        fb = build_teaching_feedback(
            _evidence("passed_unconfirmed", lesson_completed=False)
        )
        assert fb.state == "passed_unconfirmed"
        # 改版 M4：课程完成度由任务通过数推导，任务过了就直接去下一个任务，
        # 不再有「确认完成本课」这一步动作。
        assert fb.next_action == "next_task"

    def test_passed_unconfirmed_completed(self):
        fb = build_teaching_feedback(
            _evidence("passed_unconfirmed", lesson_completed=True)
        )
        assert fb.state == "passed_unconfirmed"
        assert fb.next_action == "inspect_result"

    def test_unverifiable(self):
        fb = build_teaching_feedback(_evidence("unverifiable"))
        assert fb.state == "unverifiable"
        assert fb.next_action == "retry_later"

    def test_no_evidence(self):
        fb = build_teaching_feedback(
            _evidence("no_evidence", attempt_id=None, attempt_no=None,
                      task_id=None, verdict=None)
        )
        assert fb.state == "no_evidence"
        assert fb.next_action == "inspect_result"
        assert fb.attempt_id is None

    def test_hint_level_clamped(self):
        fb = build_teaching_feedback(_evidence("execution_failed"), hint_level=5)
        assert fb.hint_level == 3
        fb1 = build_teaching_feedback(_evidence("execution_failed"), hint_level=0)
        assert fb1.hint_level == 1

    def test_field_aliases(self):
        """序列化使用 camelCase alias。"""
        fb = build_teaching_feedback(_evidence("execution_failed"))
        dumped = fb.model_dump(by_alias=True)
        assert "attemptId" in dumped
        assert "evidenceSummary" in dumped
        assert "hintLevel" in dumped
        assert "nextAction" in dumped


# =====================================================
# derive_next_action：所有路径
# =====================================================


class TestDeriveNextAction:
    @pytest.mark.parametrize(
        "state,lesson_completed,expected",
        [
            ("execution_failed", False, "retry_exercise"),
            ("execution_failed", True, "retry_exercise"),
            ("verification_failed", False, "retry_exercise"),
            ("verification_failed", True, "retry_exercise"),
            ("passed_unconfirmed", False, "next_task"),
            ("passed_unconfirmed", True, "inspect_result"),
            ("unverifiable", False, "retry_later"),
            ("unverifiable", True, "retry_later"),
            ("no_evidence", False, "inspect_result"),
            ("no_evidence", True, "inspect_result"),
        ],
    )
    def test_next_action_mapping(self, state, lesson_completed, expected):
        ev = _evidence(state, lesson_completed=lesson_completed)
        assert derive_next_action(ev) == expected


# =====================================================
# AgentService：teaching_feedback 集成（mock LLM）
# =====================================================


class TestServiceTeachingFeedback:
    """AgentService 在有证据时返回 teaching_feedback；无证据时为 None。"""

    LESSON = "polars-groupby"
    TASKS = ("t1", "t2")

    @staticmethod
    def _attempt_row(**overrides):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        base = dict(
            id=7,
            visitor_id="v1",
            lesson_slug="polars-groupby",
            task_id="t1",
            attempt_no=1,
            status="failed",
            verdict="execution_failed",
            code="x",
            actual=None,
            assertions="[]",
            created_time=datetime(2026, 7, 31, tzinfo=timezone.utc),
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def _make_service(self, *, attempt=None, passed_tasks=()):
        """构造带 workspace 仓库替身的 AgentService（不再有 practice_service）。"""
        from app.agent.service import AgentService

        repo = MagicMock()
        repo.get_attempt = AsyncMock(return_value=None)
        repo.latest_attempt = AsyncMock(return_value=attempt)
        repo.lesson_task_stats = AsyncMock(
            return_value=(set(passed_tasks), len(self.TASKS))
        )

        learner_state = AsyncMock()
        progress = MagicMock()
        progress.status = "started"
        learner_state.get_lesson_progress = AsyncMock(return_value=progress)

        return AgentService(
            workspace_repo=repo,
            learner_state_service=learner_state,
        )

    @pytest.mark.asyncio
    async def test_chat_returns_feedback_when_evidence_exists(self):
        attempt = self._attempt_row()

        service = self._make_service(attempt=attempt)

        # mock _complete 返回成功内容
        from app.agent.llm_client import LLMResult

        service._complete = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResult(content="修复建议", error_reason=None, latency_ms=0)
        )

        payload = AgentChatRequest(
            message="帮我修错",
            context=AgentContext(currentLesson=self.LESSON),
        )
        data = await service.chat(payload, visitor_id="v1")

        assert isinstance(data, AgentChatData)
        assert data.content == "修复建议"
        assert data.teaching_feedback is not None
        assert data.teaching_feedback.state == "execution_failed"
        assert data.teaching_feedback.attempt_id == 7
        assert data.teaching_feedback.next_action == "retry_exercise"

    @pytest.mark.asyncio
    async def test_chat_no_feedback_without_workspace_repo(self):
        from app.agent.service import AgentService
        from app.agent.llm_client import LLMResult

        service = AgentService()  # 无 workspace_repo
        service._complete = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResult(content="hi", error_reason=None, latency_ms=0)
        )

        payload = AgentChatRequest(message="你好")
        data = await service.chat(payload, visitor_id="v1")

        assert data.teaching_feedback is None

    @pytest.mark.asyncio
    async def test_chat_no_feedback_without_visitor_id(self):
        """降级路径未带 visitor_id 时不构造反馈（无法做归属隔离）。"""
        service = self._make_service(attempt=self._attempt_row())
        from app.agent.llm_client import LLMResult

        service._complete = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResult(content="hi", error_reason=None, latency_ms=0)
        )

        payload = AgentChatRequest(message="你好")
        data = await service.chat(payload)  # 无 visitor_id

        assert data.teaching_feedback is None

    @pytest.mark.asyncio
    async def test_hint_level_raises_with_history(self):
        """连续求助（history 中 user 消息增多）时 hint_level 升高。"""
        from app.agent.service import AgentService
        from app.agent.llm_client import LLMResult

        service = self._make_service()
        service._complete = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResult(content="hi", error_reason=None, latency_ms=0)
        )

        # 0 条 history -> level 1
        from app.agent.schemas import AgentChatMessage

        payload0 = AgentChatRequest(
            message="帮我", context=AgentContext(currentLesson="l1")
        )
        assert service._estimate_hint_level(payload0) == 1

        # 4 条 user history -> level 3
        payload4 = AgentChatRequest(
            message="帮我",
            history=[
                AgentChatMessage(role="user", content="q"),
                AgentChatMessage(role="assistant", content="a"),
                AgentChatMessage(role="user", content="q2"),
                AgentChatMessage(role="assistant", content="a2"),
                AgentChatMessage(role="user", content="q3"),
                AgentChatMessage(role="assistant", content="a3"),
                AgentChatMessage(role="user", content="q4"),
                AgentChatMessage(role="assistant", content="a4"),
            ],
            context=AgentContext(currentLesson="l1"),
        )
        assert service._estimate_hint_level(payload4) == 3
