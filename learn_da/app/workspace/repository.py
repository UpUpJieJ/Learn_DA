"""工作区只读查询（Agent 证据与工具复用）。

与 ``service.py`` 的分工：service 负责执行与写入（依赖 Runner client），本模块
只做读取，因此 Agent 侧可以在没有 Runner 的场景里安全构造它。

边界约定：
* 所有查询强制带 ``visitor_id``，不接受客户端传入的身份；
* 只返回摘要字段所需的最小数据，不把整段历史代码交给模型；
* 内容侧任务总数来自 ``load_workspace``（与运行时判定同源）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_catalog import get_content_index

from .content import WorkspaceSpec, load_workspace
from .models import TaskAttempt


def spec_for(lesson_slug: str) -> WorkspaceSpec | None:
    """取某课的工作区定义；课程不存在或没有 workspace 时返回 None。"""
    for lesson in get_content_index().lessons:
        if str(lesson.get("slug")) != lesson_slug:
            continue
        return load_workspace(lesson)
    return None


class WorkspaceReadRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _one(self, stmt) -> TaskAttempt | None:
        return (await self.db.execute(stmt)).scalars().first()

    async def get_attempt(
        self, visitor_id: str, attempt_id: int
    ) -> TaskAttempt | None:
        """按 id 取任务提交，带访客归属校验（跨访客查不到）。"""
        return await self._one(
            select(TaskAttempt)
            .where(
                TaskAttempt.id == attempt_id,
                TaskAttempt.visitor_id == visitor_id,
            )
            .limit(1)
        )

    async def latest_attempt(
        self,
        visitor_id: str,
        lesson_slug: str,
        task_id: str | None = None,
    ) -> TaskAttempt | None:
        """该课（或该任务）最近一次提交。"""
        stmt = select(TaskAttempt).where(
            TaskAttempt.visitor_id == visitor_id,
            TaskAttempt.lesson_slug == lesson_slug,
        )
        if task_id:
            stmt = stmt.where(TaskAttempt.task_id == task_id)
        return await self._one(
            stmt.order_by(TaskAttempt.created_time.desc(), TaskAttempt.id.desc()).limit(1)
        )

    async def recent_attempts(
        self,
        visitor_id: str,
        lesson_slug: str | None = None,
        limit: int = 10,
    ) -> list[TaskAttempt]:
        """最近的提交记录（新到旧），用于工具摘要。"""
        stmt = select(TaskAttempt).where(TaskAttempt.visitor_id == visitor_id)
        if lesson_slug:
            stmt = stmt.where(TaskAttempt.lesson_slug == lesson_slug)
        rows = await self.db.execute(
            stmt.order_by(TaskAttempt.created_time.desc(), TaskAttempt.id.desc()).limit(
                max(1, min(limit, 50))
            )
        )
        return list(rows.scalars().all())

    async def passed_task_ids(self, visitor_id: str, lesson_slug: str) -> set[str]:
        """该课已通过（只算 passed）的任务 id 集合。"""
        rows = await self.db.execute(
            select(TaskAttempt.task_id).where(
                TaskAttempt.visitor_id == visitor_id,
                TaskAttempt.lesson_slug == lesson_slug,
                TaskAttempt.status == "passed",
            )
        )
        return {str(item) for item in rows.scalars().all()}

    async def lesson_task_stats(
        self, visitor_id: str, lesson_slug: str
    ) -> tuple[set[str], int]:
        """(已通过任务 id 集合, 任务总数)。"""
        spec = spec_for(lesson_slug)
        total = len(spec.tasks) if spec is not None else 0
        passed = await self.passed_task_ids(visitor_id, lesson_slug)
        if spec is not None:
            known = {task.task_id for task in spec.tasks}
            passed &= known
        return passed, total

    async def progress(self, visitor_id: str) -> dict[str, Any]:
        """全量课程进度（复用 progress 模块的聚合口径）。"""
        from .progress import lesson_progress

        return await lesson_progress(self.db, visitor_id)