"""阶段 3 Task 3：Agent 交互审计持久化层。

幂等保证：相同 ``request_id`` 重放时返回已存在记录，不新增行、不重复
计入 ``ai_help``。禁止跨 visitor 查询：所有读取都带 ``visitor_id`` 过滤。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AgentInteraction


class AgentInteractionRepository:
    """Agent 交互审计的持久化访问层。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_request_id(
        self, visitor_id: str, request_id: str
    ) -> AgentInteraction | None:
        """按幂等键查询（带 visitor 过滤）。"""
        stmt = select(AgentInteraction).where(
            AgentInteraction.visitor_id == visitor_id,
            AgentInteraction.request_id == request_id,
            AgentInteraction.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(
        self, interaction_id: int, visitor_id: str
    ) -> AgentInteraction | None:
        """按主键查询（带 visitor 过滤，用于反馈端点鉴权）。"""
        stmt = select(AgentInteraction).where(
            AgentInteraction.id == interaction_id,
            AgentInteraction.visitor_id == visitor_id,
            AgentInteraction.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        *,
        visitor_id: str,
        request_id: str,
        lesson_slug: str | None = None,
        attempt_id: int | None = None,
    ) -> tuple[AgentInteraction, bool]:
        """幂等创建。返回 (interaction, created)。created=False 表示重放命中。

        先查后插；并发下由 ``request_id`` 唯一索引拦下，调用方应捕获
        IntegrityError 并按重放处理。
        """
        existing = await self.get_by_request_id(visitor_id, request_id)
        if existing is not None:
            return existing, False

        interaction = AgentInteraction(
            visitor_id=visitor_id,
            request_id=request_id,
            lesson_slug=lesson_slug,
            attempt_id=attempt_id,
        )
        self.db.add(interaction)
        await self.db.flush()
        return interaction, True

    async def fill_metrics(
        self,
        interaction: AgentInteraction,
        *,
        route: str | None = None,
        retrieval_mode: str | None = None,
        tool_names: list[str] | None = None,
        llm_latency_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        fallback_reason: str | None = None,
        evidence_state: str | None = None,
        verification_status: str | None = None,
        hint_level: int | None = None,
        next_action: str | None = None,
    ) -> None:
        """在 LLM 调用完成后回填审计指标。

        不持久化完整 prompt、完整代码、Runner token 或会话 cookie；
        只写入可观测的结构化指标。
        """
        interaction.route = route
        interaction.retrieval_mode = retrieval_mode
        interaction.tool_names = (
            json.dumps(tool_names, ensure_ascii=False) if tool_names else None
        )
        interaction.llm_latency_ms = llm_latency_ms
        interaction.input_tokens = input_tokens
        interaction.output_tokens = output_tokens
        interaction.fallback_reason = fallback_reason
        interaction.evidence_state = evidence_state
        interaction.verification_status = verification_status
        interaction.hint_level = hint_level
        interaction.next_action = next_action
        await self.db.flush()

    async def update_feedback(
        self,
        interaction: AgentInteraction,
        feedback: str,
    ) -> None:
        """更新用户反馈（upsert 语义，不新增 ai_help）。"""
        interaction.feedback = feedback
        await self.db.flush()

    async def count_by_visitor(self, visitor_id: str) -> int:
        """统计 visitor 的交互总数（供推荐聚合用）。"""
        from sqlalchemy import func

        stmt = select(func.count(AgentInteraction.id)).where(
            AgentInteraction.visitor_id == visitor_id,
            AgentInteraction.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_recent_by_lesson(
        self,
        visitor_id: str,
        lesson_slug: str,
        limit: int = 10,
    ) -> list[AgentInteraction]:
        """获取 visitor 对某课程的最近交互（供推荐读取帮助后通过率等聚合）。"""
        stmt = (
            select(AgentInteraction)
            .where(
                AgentInteraction.visitor_id == visitor_id,
                AgentInteraction.lesson_slug == lesson_slug,
                AgentInteraction.is_deleted == False,  # noqa: E712
            )
            .order_by(
                AgentInteraction.created_time.desc(),
                AgentInteraction.id.desc(),
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
