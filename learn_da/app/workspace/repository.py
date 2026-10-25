"""工作区只读查询（Agent 证据与工具复用）。

与 ``service.py`` 的分工：service 负责执行与写入（依赖 Runner client），本模块
只做读取，因此 Agent 侧可以在没有 Runner 的场景里安全构造它。

边界约定：
* 所有查询强制带 ``visitor_id``，不接受客户端传入的身份；
* 只返回摘要字段所需的最小数据，不把整段历史代码交给模型；
* 内容侧任务总数来自 ``load_workspace``（与运行时判定同源）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_catalog import get_content_index

from .content import WorkspaceSpec, load_workspace
from .hints import HintState, compute_level
from .models import HintUsage, RunEvent, TaskAttempt


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

    async def passed_after(
        self,
        visitor_id: str,
        lesson_slug: str,
        task_id: str,
        after,
    ) -> TaskAttempt | None:
        """某任务在给定时间点之后是否已经通过（用于判断"求助后是否解决"）。"""
        return await self._one(
            select(TaskAttempt)
            .where(
                TaskAttempt.visitor_id == visitor_id,
                TaskAttempt.lesson_slug == lesson_slug,
                TaskAttempt.task_id == task_id,
                TaskAttempt.status == "passed",
                TaskAttempt.created_time >= after,
            )
            .order_by(TaskAttempt.created_time.asc(), TaskAttempt.id.asc())
            .limit(1)
        )

    async def latest_run_payload(
        self, visitor_id: str, session_id: int, cell_id: str
    ) -> dict[str, Any] | None:
        """该格最近一次执行的完整响应体（``RunEvent.payload``）。

        提示文案需要「代码没跑通」时的真实报错——断言结果是 ``skipped``，
        只有单元格的 ``stderr`` 里才有可读的原因（如 ``ColumnNotFoundError``）。
        """
        payload = (
            await self.db.execute(
                select(RunEvent.payload)
                .where(
                    RunEvent.visitor_id == visitor_id,
                    RunEvent.session_id == session_id,
                    RunEvent.cell_id == cell_id,
                )
                .order_by(RunEvent.created_time.desc(), RunEvent.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    async def progress(self, visitor_id: str) -> dict[str, Any]:
        """全量课程进度（复用 progress 模块的聚合口径）。"""
        from .progress import lesson_progress

        return await lesson_progress(self.db, visitor_id)

    # ------------------------------------------------------------------
    # 分级提示（ladder，改版 E2）
    # ------------------------------------------------------------------

    async def hint_usage_count(
        self, visitor_id: str, lesson_slug: str, task_id: str
    ) -> int:
        """该任务已经发放过几层提示（服务端权威）。"""
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(HintUsage)
                .where(
                    HintUsage.visitor_id == visitor_id,
                    HintUsage.lesson_slug == lesson_slug,
                    HintUsage.task_id == task_id,
                )
            )
        ).scalar()
        return int(total or 0)

    async def last_hint_at(self, visitor_id: str, lesson_slug: str, task_id: str):
        """该任务最后一次提示的时间（没有则 None）。"""
        return (
            await self.db.execute(
                select(HintUsage.created_time)
                .where(
                    HintUsage.visitor_id == visitor_id,
                    HintUsage.lesson_slug == lesson_slug,
                    HintUsage.task_id == task_id,
                )
                .order_by(HintUsage.created_time.desc(), HintUsage.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def failures_since(
        self,
        visitor_id: str,
        lesson_slug: str,
        task_id: str,
        after,
    ) -> int:
        """该任务在给定时间点之后失败了几次（``after`` 为 None 时算全部）。"""
        stmt = select(func.count()).select_from(TaskAttempt).where(
            TaskAttempt.visitor_id == visitor_id,
            TaskAttempt.lesson_slug == lesson_slug,
            TaskAttempt.task_id == task_id,
            TaskAttempt.status != "passed",
        )
        if after is not None:
            stmt = stmt.where(TaskAttempt.created_time >= after)
        total = (await self.db.execute(stmt)).scalar()
        return int(total or 0)

    async def hint_state(
        self, visitor_id: str, lesson_slug: str, task_id: str
    ) -> HintState:
        """按设计稿公式算「这一次点提示能拿到第几层」。

        ``level = min(3, 1 + failures_since_last_hint + hints_used)``
        —— 失败次数来自 ``task_attempts``，已用层数来自 ``hint_usages``。
        """
        hints_used = await self.hint_usage_count(visitor_id, lesson_slug, task_id)
        last_hint_at = await self.last_hint_at(visitor_id, lesson_slug, task_id)
        failures = await self.failures_since(
            visitor_id, lesson_slug, task_id, last_hint_at
        )
        return HintState(
            task_id=task_id,
            failures_since_last_hint=failures,
            hints_used=hints_used,
            level=compute_level(failures, hints_used),
            last_hint_at=last_hint_at,
        )

    async def hint_states(
        self, visitor_id: str, lesson_slug: str, task_ids: list[str]
    ) -> dict[str, HintState]:
        """一次算完一课所有任务的层级（快照用，避免逐任务查三次）。"""
        if not task_ids:
            return {}
        wanted = set(task_ids)

        used_rows = await self.db.execute(
            select(HintUsage.task_id, func.count())
            .where(
                HintUsage.visitor_id == visitor_id,
                HintUsage.lesson_slug == lesson_slug,
                HintUsage.task_id.in_(wanted),
            )
            .group_by(HintUsage.task_id)
        )
        hints_used = {str(task): int(count) for task, count in used_rows.all()}

        last_rows = await self.db.execute(
            select(HintUsage.task_id, func.max(HintUsage.created_time))
            .where(
                HintUsage.visitor_id == visitor_id,
                HintUsage.lesson_slug == lesson_slug,
                HintUsage.task_id.in_(wanted),
            )
            .group_by(HintUsage.task_id)
        )
        last_hint = {str(task): stamp for task, stamp in last_rows.all()}

        fail_rows = await self.db.execute(
            select(TaskAttempt.task_id, func.count())
            .where(
                TaskAttempt.visitor_id == visitor_id,
                TaskAttempt.lesson_slug == lesson_slug,
                TaskAttempt.task_id.in_(wanted),
                TaskAttempt.status != "passed",
            )
            .group_by(TaskAttempt.task_id)
        )
        all_failures = {str(task): int(count) for task, count in fail_rows.all()}

        # 「上一次提示之后的失败次数」需要按时间切分，逐任务再查一次
        # （任务数 ≤ 40，且只在带 hint 的课上发生，代价可接受）。
        states: dict[str, HintState] = {}
        for task_id in task_ids:
            used = hints_used.get(task_id, 0)
            after = last_hint.get(task_id)
            if after is None:
                failures = all_failures.get(task_id, 0)
            else:
                failures = await self.failures_since(
                    visitor_id, lesson_slug, task_id, after
                )
            states[task_id] = HintState(
                task_id=task_id,
                failures_since_last_hint=failures,
                hints_used=used,
                level=compute_level(failures, used),
                last_hint_at=after,
            )
        return states