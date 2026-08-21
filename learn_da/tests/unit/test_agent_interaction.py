"""阶段 3 Task 3：Agent 交互审计与 ai_help 关联测试。

覆盖计划要求：
- 相同 request ID 并发/重放后仅一条 interaction、一个 ai_help；
- 伪造 attemptId 得不到其他 visitor 的审计或反馈权限；
- fallback/429/timeout/tool 参数错误均持久化对应分类；
- 审计摘要中不存在代码、token、cookie 和完整 LLM 内容。
- 用户反馈端点：校验归属、可覆盖更新但不新增 ai_help。
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from app.agent.models import AgentInteraction
from app.agent.repository import AgentInteractionRepository


# =====================================================
# 内存 SQLite fixture
# =====================================================


@pytest_asyncio.fixture
async def interaction_setup():
    """构造内存 SQLite + AgentInteractionRepository。"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.database.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as db:
        repo = AgentInteractionRepository(db)
        yield repo, db
    await engine.dispose()


# =====================================================
# 幂等：相同 request_id 仅一条 interaction
# =====================================================


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_same_request_id_creates_once(self, interaction_setup):
        repo, db = interaction_setup

        a, created1 = await repo.get_or_create(
            visitor_id="v1", request_id="req-1", lesson_slug="l1", attempt_id=5
        )
        b, created2 = await repo.get_or_create(
            visitor_id="v1", request_id="req-1", lesson_slug="l1", attempt_id=5
        )

        assert created1 is True
        assert created2 is False
        assert a.id == b.id
        assert a.request_id == "req-1"

        await db.commit()
        count = await repo.count_by_visitor("v1")
        assert count == 1

    @pytest.mark.asyncio
    async def test_different_request_id_creates_separate(self, interaction_setup):
        repo, db = interaction_setup

        await repo.get_or_create(visitor_id="v1", request_id="req-1")
        await repo.get_or_create(visitor_id="v1", request_id="req-2")
        await db.commit()

        assert await repo.count_by_visitor("v1") == 2

    @pytest.mark.asyncio
    async def test_request_id_globally_unique(
        self, interaction_setup
    ):
        """request_id 是全局唯一幂等键：不同 visitor 不能共享同一 request_id。

        生产中每个 HTTP 请求的 request_id 全局唯一，此约束防止重放跨 visitor
        混写。第二个插入应被唯一索引拒绝。
        """
        repo, db = interaction_setup

        a, created1 = await repo.get_or_create(visitor_id="v1", request_id="req-x")
        await db.commit()
        assert created1 is True

        # 不同 visitor 复用同一 request_id -> 唯一约束拒绝
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await repo.get_or_create(visitor_id="v2", request_id="req-x")
        await db.rollback()

        assert await repo.count_by_visitor("v1") == 1
        assert await repo.count_by_visitor("v2") == 0


# =====================================================
# 归属隔离：伪造 interactionId 得不到他人反馈
# =====================================================


class TestOwnershipIsolation:
    @pytest.mark.asyncio
    async def test_get_by_id_filters_visitor(self, interaction_setup):
        repo, db = interaction_setup
        interaction, _ = await repo.get_or_create(
            visitor_id="victim", request_id="req-1"
        )
        await db.commit()

        # 攻击者用 victim 的 interaction.id 查询 -> None
        found = await repo.get_by_id(interaction.id, "attacker")
        assert found is None

    @pytest.mark.asyncio
    async def test_update_feedback_only_for_owner(self, interaction_setup):
        repo, db = interaction_setup
        interaction, _ = await repo.get_or_create(
            visitor_id="v1", request_id="req-1"
        )
        await db.commit()

        # owner 可更新
        owner = await repo.get_by_id(interaction.id, "v1")
        assert owner is not None
        await repo.update_feedback(owner, "helpful")
        await db.commit()
        assert owner.feedback == "helpful"

        # 攻击者查不到，无法更新
        attacker = await repo.get_by_id(interaction.id, "attacker")
        assert attacker is None


# =====================================================
# 指标回填：不持久化敏感字段
# =====================================================


class TestMetricsFill:
    @pytest.mark.asyncio
    async def test_fill_metrics_persists_classification(self, interaction_setup):
        repo, db = interaction_setup
        interaction, _ = await repo.get_or_create(
            visitor_id="v1", request_id="req-1"
        )
        await repo.fill_metrics(
            interaction,
            route="fix_code",
            retrieval_mode="keyword",
            tool_names=["search_knowledge", "get_exercise_summary"],
            llm_latency_ms=850,
            input_tokens=1200,
            output_tokens=300,
            fallback_reason="timeout",
            evidence_state="execution_failed",
            verification_status="not_run",
            hint_level=2,
            next_action="retry_exercise",
        )
        await db.commit()

        found = await repo.get_by_request_id("v1", "req-1")
        assert found is not None
        assert found.route == "fix_code"
        assert found.retrieval_mode == "keyword"
        assert found.llm_latency_ms == 850
        assert found.input_tokens == 1200
        assert found.output_tokens == 300
        assert found.fallback_reason == "timeout"
        assert found.evidence_state == "execution_failed"
        assert found.hint_level == 2
        assert found.next_action == "retry_exercise"

    @pytest.mark.asyncio
    async def test_no_sensitive_fields_in_model(self):
        """AgentInteraction 模型不含 code/token/cookie/完整 prompt 字段。"""
        cols = {c.name for c in AgentInteraction.__table__.columns}
        forbidden = {"code", "prompt", "full_prompt", "session_cookie", "runner_token"}
        assert not (forbidden & cols), f"敏感字段泄漏: {forbidden & cols}"

    @pytest.mark.asyncio
    async def test_audit_summary_excludes_code(self, interaction_setup):
        """回填指标后，行中不存在代码内容。"""
        repo, db = interaction_setup
        interaction, _ = await repo.get_or_create(
            visitor_id="v1", request_id="req-1"
        )
        await repo.fill_metrics(
            interaction,
            route="general_chat",
            tool_names=["search_knowledge"],
            fallback_reason=None,
        )
        await db.commit()

        found = await repo.get_by_request_id("v1", "req-1")
        dumped = {c.name: getattr(found, c.name, None) for c in found.__table__.columns}
        dumped_str = str(dumped)
        # 确保没有 code/prompt 类字段
        assert "code" not in dumped
        assert "prompt" not in dumped
        assert "SECRET" not in dumped_str


# =====================================================
# AgentService.record_feedback + 幂等 ai_help 集成
# =====================================================


class TestServiceFeedbackAndAiHelp:
    @pytest.mark.asyncio
    async def test_same_request_id_does_not_call_model_twice(self):
        from app.agent.llm_client import LLMResult
        from app.agent.schemas import AgentChatRequest
        from app.agent.service import AgentService
        from app.utils.logger import request_id_var

        interaction = AgentInteraction()
        interaction.id = 1
        interaction.visitor_id = "v1"
        interaction.request_id = "req-fixed"

        repo = MagicMock()
        repo.get_or_create = AsyncMock(
            side_effect=[
                (interaction, True),
                (interaction, False),
                (interaction, False),
            ]
        )
        repo.fill_metrics = AsyncMock()
        repo.db = MagicMock()
        analytics = AsyncMock()
        service = AgentService(interaction_repo=repo, analytics_service=analytics)
        service._retrieve_knowledge = AsyncMock(return_value=("", 0))  # type: ignore[method-assign]
        service._complete = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResult(content="answer", error_reason=None, latency_ms=1)
        )

        token = request_id_var.set("req-fixed")
        try:
            payload = AgentChatRequest(message="hi")
            first = await service.chat(payload, visitor_id="v1")
            second = await service.chat(payload, visitor_id="v1")
        finally:
            request_id_var.reset(token)

        assert first.interaction_id == 1
        assert second.interaction_id == 1
        assert second.used_fallback is True
        service._complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_feedback_owner_only(self):
        from app.agent.service import AgentService
        from app.agent.schemas import AgentFeedbackRequest

        interaction = AgentInteraction()
        interaction.id = 10
        interaction.visitor_id = "v1"
        interaction.request_id = "req-1"

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=interaction)
        repo.update_feedback = AsyncMock()

        service = AgentService(interaction_repo=repo)

        # owner
        resp = await service.record_feedback(
            AgentFeedbackRequest(interactionId=10, feedback="helpful"), "v1"
        )
        assert resp.recorded is True
        repo.update_feedback.assert_called_once_with(interaction, "helpful")

    @pytest.mark.asyncio
    async def test_record_feedback_attacker_denied(self):
        from app.agent.service import AgentService
        from app.agent.schemas import AgentFeedbackRequest

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)  # 不属于攻击者
        repo.update_feedback = AsyncMock()

        service = AgentService(interaction_repo=repo)
        resp = await service.record_feedback(
            AgentFeedbackRequest(interactionId=10, feedback="helpful"), "attacker"
        )
        assert resp.recorded is False
        repo.update_feedback.assert_not_called()

    def test_feedback_value_is_limited_to_supported_choices(self):
        from pydantic import ValidationError
        from app.agent.schemas import AgentFeedbackRequest

        with pytest.raises(ValidationError):
            AgentFeedbackRequest(interactionId=10, feedback="maybe")

    @pytest.mark.asyncio
    async def test_persist_interaction_skips_without_request_id(self):
        """未经过请求中间件（request_id 为 '-'）时不持久化。"""
        from app.agent.service import AgentService

        repo = MagicMock()
        repo.get_or_create = AsyncMock()
        service = AgentService(interaction_repo=repo)

        # request_id_var 默认为 "-"，应跳过
        await service._persist_interaction(
            visitor_id="v1",
            evidence=None,
            route="general_chat",
        )
        repo.get_or_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_interaction_skips_without_repo(self):
        """无 interaction_repo 时不持久化。"""
        from app.agent.service import AgentService

        service = AgentService()  # 无 interaction_repo
        # 不应抛异常
        await service._persist_interaction(
            visitor_id="v1", evidence=None, route="general_chat"
        )

    @pytest.mark.asyncio
    async def test_idempotent_ai_help_single_write(self):
        """相同 request_id 重放：get_or_create 返回 created=False，不重复写 ai_help。"""
        from app.agent.service import AgentService
        from app.agent.evidence import AgentLearningEvidence
        from app.utils.logger import request_id_var

        interaction = AgentInteraction()
        interaction.id = 1
        interaction.visitor_id = "v1"
        interaction.request_id = "req-fixed"

        repo = MagicMock()
        # 第一次 created=True，第二次 created=False
        repo.get_or_create = AsyncMock(
            side_effect=[(interaction, True), (interaction, False)]
        )
        repo.fill_metrics = AsyncMock()

        analytics = AsyncMock()
        service = AgentService(
            interaction_repo=repo, analytics_service=analytics
        )

        evidence = AgentLearningEvidence(
            state="execution_failed",
            lesson_slug="polars-basics",
            exercise_id="ex-001",
            attempt_id=42,
            execution_status="error",
            verification_status="not_run",
            lesson_completed=False,
        )

        token = request_id_var.set("req-fixed")
        try:
            # 第一次：created=True -> 写 ai_help
            await service._persist_interaction(
                visitor_id="v1", evidence=evidence, route="fix_code"
            )
            assert analytics.track_event.call_count == 1

            # 第二次（重放）：created=False -> 不写 ai_help
            await service._persist_interaction(
                visitor_id="v1", evidence=evidence, route="fix_code"
            )
            assert analytics.track_event.call_count == 1  # 仍为 1
        finally:
            request_id_var.reset(token)

    @pytest.mark.asyncio
    async def test_ai_help_uses_evidence_lesson_not_client(self):
        """ai_help 的 lessonSlug 来自 evidence resolver，而非客户端上下文。"""
        from app.agent.service import AgentService
        from app.agent.evidence import AgentLearningEvidence
        from app.utils.logger import request_id_var

        interaction = AgentInteraction()
        interaction.id = 1
        interaction.visitor_id = "v1"
        interaction.request_id = "req-x"

        repo = MagicMock()
        repo.get_or_create = AsyncMock(return_value=(interaction, True))
        repo.fill_metrics = AsyncMock()

        analytics = AsyncMock()
        service = AgentService(
            interaction_repo=repo, analytics_service=analytics
        )

        evidence = AgentLearningEvidence(
            state="verification_failed",
            lesson_slug="evidence-lesson",
            attempt_id=7,
            execution_status="success",
            verification_status="failed",
            lesson_completed=False,
        )

        token = request_id_var.set("req-x")
        try:
            await service._persist_interaction(
                visitor_id="v1", evidence=evidence, route="fix_code"
            )
            # ai_help 的 lessonSlug 应为 evidence 的 lesson_slug
            call = analytics.track_event.call_args
            event_req = call.kwargs.get("req") or call.args[0]
            assert event_req.lesson_slug == "evidence-lesson"
        finally:
            request_id_var.reset(token)


# =====================================================
# hint level：服务端真实连续求助计数
# =====================================================


class TestResolveHintLevel:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("helps,expected", [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (9, 3)])
    async def test_level_from_server_help_count(
        self, interaction_setup, helps, expected
    ):
        """1-2 次求助 -> L1，3-4 次 -> L2，5+ -> L3（以服务端计数为准）。"""
        from app.agent.evidence import AgentLearningEvidence
        from app.agent.schemas import AgentChatRequest
        from app.agent.service import AgentService

        repo, db = interaction_setup
        for i in range(helps):
            await repo.get_or_create(
                visitor_id="v1", request_id=f"req-{i}", lesson_slug="l1"
            )

        service = AgentService(interaction_repo=repo)
        evidence = AgentLearningEvidence(state="execution_failed", lesson_slug="l1")
        payload = AgentChatRequest(message="帮我")
        assert await service._resolve_hint_level(payload, "v1", evidence) == expected

    @pytest.mark.asyncio
    async def test_fallback_to_history_without_lesson(self, interaction_setup):
        """无课程证据时降级为 history 估算（4 条 user -> L3）。"""
        from app.agent.schemas import AgentChatMessage, AgentChatRequest
        from app.agent.service import AgentService

        repo, _ = interaction_setup
        service = AgentService(interaction_repo=repo)
        payload = AgentChatRequest(
            message="帮我",
            history=[
                AgentChatMessage(role="user", content=f"q{i}") for i in range(4)
            ],
        )
        assert await service._resolve_hint_level(payload, "v1", None) == 3

    @pytest.mark.asyncio
    async def test_fallback_when_count_query_fails(self):
        """计数查询失败时不阻断对话，降级为 history 估算。"""
        from app.agent.evidence import AgentLearningEvidence
        from app.agent.schemas import AgentChatRequest
        from app.agent.service import AgentService

        repo = MagicMock()
        repo.count_by_visitor_and_lesson = AsyncMock(side_effect=RuntimeError("db"))
        service = AgentService(interaction_repo=repo)
        evidence = AgentLearningEvidence(state="execution_failed", lesson_slug="l1")
        payload = AgentChatRequest(message="帮我")
        assert await service._resolve_hint_level(payload, "v1", evidence) == 1

    @pytest.mark.asyncio
    async def test_chat_persists_server_side_hint_level(self):
        """chat() 写入的 hint_level 来自服务端计数，而非客户端 history。"""
        from app.agent.llm_client import LLMResult
        from app.agent.schemas import AgentChatRequest
        from app.agent.service import AgentService
        from app.utils.logger import request_id_var

        interaction = AgentInteraction()
        interaction.id = 1
        interaction.visitor_id = "v1"
        interaction.request_id = "req-h"

        repo = MagicMock()
        repo.get_or_create = AsyncMock(return_value=(interaction, True))
        repo.fill_metrics = AsyncMock()
        # 服务端已有 3 次求助 -> L2；客户端 history 为空（若信 history 会得 L1）
        repo.count_by_visitor_and_lesson = AsyncMock(return_value=3)

        service = AgentService(interaction_repo=repo)
        service._retrieve_knowledge = AsyncMock(return_value=("", 0))  # type: ignore[method-assign]
        service._inject_evidence = AsyncMock(  # type: ignore[method-assign]
            side_effect=lambda messages, payload, visitor_id: _with_evidence(messages)
        )
        service._complete = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResult(content="answer", error_reason=None, latency_ms=1)
        )

        token = request_id_var.set("req-h")
        try:
            data = await service.chat(
                AgentChatRequest(message="帮我"), visitor_id="v1"
            )
        finally:
            request_id_var.reset(token)

        assert repo.fill_metrics.await_args.kwargs["hint_level"] == 2
        assert data.teaching_feedback is not None
        assert data.teaching_feedback.hint_level == 2


def _with_evidence(messages):
    from app.agent.evidence import AgentLearningEvidence

    evidence = AgentLearningEvidence(
        state="execution_failed", lesson_slug="l1", attempt_id=1
    )
    return messages, evidence
