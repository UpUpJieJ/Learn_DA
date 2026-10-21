"""学习工作区服务层（改版 M1）。

职责：
* 按课程内容（frontmatter ``workspace`` 块）创建/复用会话与单元格；
* 编辑单元格后**级联失效**后续单元格（严格顺序语义）；
* 把执行请求重放式地转发给 Runner，并落 ``run_events``（幂等）；
* 任务提交落 ``task_attempts``（新的教学证据）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_catalog import get_content_index
from app.sandbox.client import RunnerClient

from .content import (
    WorkspaceContentError,
    WorkspaceSpec,
    WorkspaceTask,
    dataset_payload,
    load_workspace,
    runtime_source,
)
from .models import LessonSession, RunEvent, SessionCell, TaskAttempt
from .schemas import (
    AssertionResult,
    CellPayload,
    CellRunResult,
    RunResponse,
    SessionSnapshot,
    TaskPayload,
)


class WorkspaceNotFound(Exception):
    """课程或会话不存在。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _runner_uuid(request_id: str) -> str:
    """Runner 契约要求 UUID；客户端传的不合规 id 用命名空间 UUID 兜底。"""
    try:
        return str(uuid.UUID(request_id))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"learn-da:{request_id}"))


class WorkspaceService:
    def __init__(self, db: AsyncSession, runner_client: RunnerClient) -> None:
        self.db = db
        self.runner = runner_client

    async def _commit(self) -> None:
        """提交事务；测试用外层事务包裹时交给调用方托管（只 flush）。"""
        if getattr(self.db, "info", {}).get("external_transaction"):
            await self.db.flush()
            return
        await self.db.commit()

    # ------------------------------------------------------------------
    # 内容
    # ------------------------------------------------------------------

    def lesson(self, slug: str) -> dict[str, Any]:
        for item in get_content_index().lessons:
            if item.get("slug") == slug:
                return item
        raise WorkspaceNotFound(f"课程不存在：{slug}")

    def spec(self, slug: str) -> WorkspaceSpec:
        spec = load_workspace(self.lesson(slug))
        if spec is None:
            raise WorkspaceNotFound(f"课程 {slug} 尚未提供工作区练习")
        return spec

    # ------------------------------------------------------------------
    # 会话
    # ------------------------------------------------------------------

    async def _session(self, visitor_id: str, session_id: int) -> LessonSession:
        stmt = select(LessonSession).where(
            LessonSession.id == session_id,
            LessonSession.visitor_id == visitor_id,
        )
        found = (await self.db.execute(stmt)).scalar_one_or_none()
        if found is None:
            raise WorkspaceNotFound(f"会话不存在：{session_id}")
        return found

    async def _cells(self, session_id: int) -> list[SessionCell]:
        stmt = (
            select(SessionCell)
            .where(SessionCell.session_id == session_id)
            .order_by(SessionCell.position)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_or_create(
        self, visitor_id: str, lesson_slug: str
    ) -> tuple[LessonSession, WorkspaceSpec]:
        spec = self.spec(lesson_slug)
        version = get_content_index().content_version
        stmt = select(LessonSession).where(
            LessonSession.visitor_id == visitor_id,
            LessonSession.lesson_slug == lesson_slug,
        )
        session = (await self.db.execute(stmt)).scalar_one_or_none()

        if session is None:
            session = LessonSession(
                visitor_id=visitor_id,
                lesson_slug=lesson_slug,
                content_version=version,
                status="active",
            )
            self.db.add(session)
            await self.db.flush()
            for position, cell in enumerate(spec.cells):
                self.db.add(
                    SessionCell(
                        session_id=session.id,
                        cell_id=cell.cell_id,
                        position=position,
                        kind=cell.kind,
                        task_id=cell.task_id,
                        language=cell.language,
                        code=cell.code,
                        status="stale",
                    )
                )
            await self._commit()
            await self.db.refresh(session)
            return session, spec

        # 内容版本变了：保留学员代码，只记录新版本（单元格结构由内容决定，
        # 缺失的新格子在下一次 snapshot 时补建）。
        if session.content_version != version:
            session.content_version = version
        existing = {cell.cell_id for cell in await self._cells(session.id)}
        for position, cell in enumerate(spec.cells):
            if cell.cell_id not in existing:
                self.db.add(
                    SessionCell(
                        session_id=session.id,
                        cell_id=cell.cell_id,
                        position=position,
                        kind=cell.kind,
                        task_id=cell.task_id,
                        language=cell.language,
                        code=cell.code,
                        status="stale",
                    )
                )
        await self._commit()
        return session, spec

    async def snapshot(self, visitor_id: str, session_id: int) -> SessionSnapshot:
        session = await self._session(visitor_id, session_id)
        spec = self.spec(session.lesson_slug)
        cells = await self._cells(session.id)

        attempts = list(
            (
                await self.db.execute(
                    select(TaskAttempt)
                    .where(TaskAttempt.session_id == session.id)
                    .order_by(TaskAttempt.attempt_no)
                )
            )
            .scalars()
            .all()
        )
        latest: dict[str, TaskAttempt] = {}
        for attempt in attempts:
            latest[attempt.task_id] = attempt

        by_id = {cell.cell_id: cell for cell in cells}
        task_payloads: list[TaskPayload] = []
        for task in spec.tasks:
            cell = by_id.get(task.cell_id)
            attempt = latest.get(task.task_id)
            status = "todo"
            if attempt is not None:
                if attempt.status == "passed" and cell is not None and cell.status == "ok":
                    status = "passed"
                elif attempt.status == "passed":
                    # 代码改过 → 结论需复核，回到 todo（视图层用 stale_from 提示）
                    status = "todo"
                elif attempt.status == "failed":
                    status = "failed"
                elif attempt.status == "skipped":
                    status = "skipped"
            task_payloads.append(
                TaskPayload(
                    task_id=task.task_id,
                    title=task.title,
                    cell_id=task.cell_id,
                    objective=task.objective,
                    status=status,
                )
            )

        stale_from = next((cell.cell_id for cell in cells if cell.status == "stale"), None)
        return SessionSnapshot(
            session_id=session.id,
            lesson_slug=session.lesson_slug,
            content_version=session.content_version,
            cells=[
                CellPayload(
                    cell_id=cell.cell_id,
                    position=cell.position,
                    kind=cell.kind,
                    task_id=cell.task_id,
                    language=cell.language,
                    code=cell.code,
                    status=cell.status,
                    has_assertions=bool(spec.assertions_for_cell(cell.cell_id)),
                )
                for cell in cells
            ],
            tasks=task_payloads,
            datasets=list(spec.datasets),
            stale_from=stale_from,
        )

    async def update_cell(
        self, visitor_id: str, session_id: int, cell_id: str, code: str
    ) -> SessionSnapshot:
        session = await self._session(visitor_id, session_id)
        cells = await self._cells(session.id)
        target = next((cell for cell in cells if cell.cell_id == cell_id), None)
        if target is None:
            raise WorkspaceNotFound(f"单元格不存在：{cell_id}")
        if target.code != code:
            target.code = code
            # 严格顺序：改了第 k 格，这一格自己（旧结果对应旧代码）与其后所有格子都失效。
            for cell in cells:
                if cell.position >= target.position and cell.status != "stale":
                    cell.status = "stale"
        await self._commit()
        return await self.snapshot(visitor_id, session_id)

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    async def _cached_run(self, visitor_id: str, request_id: str) -> dict | None:
        stmt = select(RunEvent).where(
            RunEvent.visitor_id == visitor_id,
            RunEvent.request_id == request_id,
        )
        event = (await self.db.execute(stmt)).scalar_one_or_none()
        if event is None:
            return None
        try:
            return json.loads(event.payload)
        except json.JSONDecodeError:
            return None

    async def _run(
        self,
        visitor_id: str,
        session: LessonSession,
        spec: WorkspaceSpec,
        cell_id: str,
        request_id: str,
        *,
        task: WorkspaceTask | None,
        record_attempt: bool,
    ) -> RunResponse:
        cached = await self._cached_run(visitor_id, request_id)
        if cached is not None:
            return RunResponse.model_validate(cached)

        try:
            spec.cell(cell_id)
        except WorkspaceContentError as exc:
            raise WorkspaceNotFound(str(exc)) from exc
        cells = await self._cells(session.id)
        index = next((i for i, c in enumerate(cells) if c.cell_id == cell_id), None)
        if index is None:
            raise WorkspaceNotFound(f"单元格不存在：{cell_id}")
        prefix = cells[: index + 1]

        payload = {
            "requestId": _runner_uuid(request_id),
            "cells": [
                {"cellId": cell.cell_id, "code": cell.code, "language": cell.language}
                for cell in prefix
            ],
            "stopAt": cell_id,
            "datasets": dataset_payload(spec.datasets),
            "runtime": runtime_source(),
            "assertions": list(task.assertions) if task is not None else [],
            "refs": {},
        }
        raw = await self.runner.execute_session(payload)

        duration_ms = int(raw.get("durationMs") or 0)
        cell_results = [
            CellRunResult(
                cell_id=str(item.get("cellId", "")),
                status=str(item.get("status", "error")),
                stdout=str(item.get("stdout") or ""),
                stderr=str(item.get("stderr") or ""),
                error_type=item.get("errorType"),
                duration_ms=int(item.get("durationMs") or 0),
                truncated=bool(item.get("truncated")),
            )
            for item in raw.get("cells") or []
        ]
        assertions = [
            AssertionResult(
                id=str(item.get("id", "")),
                type=item.get("type"),
                title=str(item.get("title") or ""),
                status=item.get("status", "skipped"),
                actual=item.get("actual"),
                detail=item.get("detail"),
                duration_ms=int(item.get("durationMs") or 0),
            )
            for item in raw.get("assertions") or []
        ]
        verdict = raw.get("verdict") or "execution_failed"

        now = _now()
        for cell in cells:
            result = next((r for r in cell_results if r.cell_id == cell.cell_id), None)
            if result is not None:
                cell.status = "ok" if result.status == "success" else "failed"
                cell.last_run_at = now
            elif cell.position > (cells[index].position if index is not None else -1):
                cell.status = "stale"

        response = RunResponse(
            request_id=request_id,
            session_id=session.id,
            cell_id=cell_id,
            verdict=verdict,
            cells=cell_results,
            assertions=assertions,
            assertions_skipped=bool(raw.get("assertionsSkipped")),
            duration_ms=duration_ms,
            error=str(raw.get("error") or ""),
        )

        if task is not None and record_attempt:
            attempt_no = int(
                (
                    await self.db.execute(
                        select(func.count())
                        .select_from(TaskAttempt)
                        .where(
                            TaskAttempt.session_id == session.id,
                            TaskAttempt.task_id == task.task_id,
                        )
                    )
                ).scalar()
                or 0
            ) + 1
            attempt_status = (
                "passed"
                if verdict == "passed"
                else ("skipped" if response.assertions_skipped else "failed")
            )
            first_actual = next(
                (a.actual for a in assertions if a.status != "passed" and a.actual),
                "",
            )
            self.db.add(
                TaskAttempt(
                    visitor_id=visitor_id,
                    session_id=session.id,
                    lesson_slug=session.lesson_slug,
                    task_id=task.task_id,
                    attempt_no=attempt_no,
                    status=attempt_status,
                    code=cells[index].code,
                    actual=first_actual or "",
                    assertions=json.dumps(
                        [a.model_dump(by_alias=True) for a in assertions], ensure_ascii=False
                    ),
                )
            )
            response.task_status = attempt_status

        self.db.add(
            RunEvent(
                visitor_id=visitor_id,
                session_id=session.id,
                request_id=request_id,
                cell_id=cell_id,
                stop_at=cell_id,
                verdict=verdict,
                duration_ms=duration_ms,
                # 存完整响应体：同一 request_id 重放时直接还原（含 task_status）
                payload=json.dumps(response.model_dump(by_alias=True), ensure_ascii=False),
            )
        )
        await self._commit()
        return response

    async def run_cell(
        self, visitor_id: str, session_id: int, cell_id: str, request_id: str
    ) -> RunResponse:
        session = await self._session(visitor_id, session_id)
        spec = self.spec(session.lesson_slug)
        task = next((task for task in spec.tasks if task.cell_id == cell_id), None)
        return await self._run(
            visitor_id,
            session,
            spec,
            cell_id,
            request_id,
            task=task,
            record_attempt=False,
        )

    async def submit_task(
        self, visitor_id: str, session_id: int, task_id: str, request_id: str
    ) -> RunResponse:
        session = await self._session(visitor_id, session_id)
        spec = self.spec(session.lesson_slug)
        try:
            task = spec.task(task_id)
        except WorkspaceContentError as exc:
            raise WorkspaceNotFound(str(exc)) from exc
        response = await self._run(
            visitor_id,
            session,
            spec,
            task.cell_id,
            request_id,
            task=task,
            record_attempt=True,
        )
        return response