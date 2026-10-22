"""学习工作区 API（改版 M1）。

路由由 ``auto_register_routers()`` 自动挂载（``app/<module>/router.py``）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.database import get_db
from app.core.session import get_anonymous_visitor_id
from app.sandbox.client import RunnerUnavailableError
from app.utils.base_response import StdResp

from .content import WorkspaceContentError
from .progress import learning_report, lesson_progress
from .schemas import (
    CreateSessionRequest,
    RunCellRequest,
    SubmitTaskRequest,
    UpdateCellRequest,
)
from .service import WorkspaceNotFound, WorkspaceService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["workspace"])


def get_service(
    request: Request, db: AsyncSession = Depends(get_db)
) -> WorkspaceService:
    return WorkspaceService(db=db, runner_client=request.app.state.runner_client)


@router.get("/progress")
async def get_progress(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """课程地图用：每门课的任务级进度。"""
    return StdResp.success(data=await lesson_progress(db, visitor_id))


@router.get("/report")
async def get_report(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """学习报告用：真实能力、失败模式与最近提交。"""
    return StdResp.success(data=await learning_report(db, visitor_id))


@router.post("/sessions")
async def create_session(
    payload: CreateSessionRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    service: WorkspaceService = Depends(get_service),
):
    """创建或复用一个课程会话，返回完整快照。"""
    try:
        session, _ = await service.get_or_create(visitor_id, payload.lesson_slug)
        snapshot = await service.snapshot(visitor_id, session.id)
    except WorkspaceNotFound as exc:
        return StdResp.not_found(msg=str(exc))
    except WorkspaceContentError as exc:
        return StdResp.error(msg=str(exc), code=400)
    return StdResp.success(data=snapshot.model_dump(by_alias=True))


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    service: WorkspaceService = Depends(get_service),
):
    try:
        snapshot = await service.snapshot(visitor_id, session_id)
    except WorkspaceNotFound as exc:
        return StdResp.not_found(msg=str(exc))
    except WorkspaceContentError as exc:
        return StdResp.error(msg=str(exc), code=400)
    return StdResp.success(data=snapshot.model_dump(by_alias=True))


@router.put("/sessions/{session_id}/cells/{cell_id}")
async def update_cell(
    session_id: int,
    cell_id: str,
    payload: UpdateCellRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    service: WorkspaceService = Depends(get_service),
):
    """保存单元格代码；改动会让后续单元格失效（严格顺序）。"""
    try:
        snapshot = await service.update_cell(
            visitor_id, session_id, cell_id, payload.code
        )
    except WorkspaceNotFound as exc:
        return StdResp.not_found(msg=str(exc))
    except WorkspaceContentError as exc:
        return StdResp.error(msg=str(exc), code=400)
    return StdResp.success(data=snapshot.model_dump(by_alias=True))


@router.post("/sessions/{session_id}/cells/{cell_id}/run")
async def run_cell(
    session_id: int,
    cell_id: str,
    payload: RunCellRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    service: WorkspaceService = Depends(get_service),
):
    """从第一格重放到该格并返回逐格输出。"""
    try:
        result = await service.run_cell(
            visitor_id, session_id, cell_id, payload.request_id
        )
    except WorkspaceNotFound as exc:
        return StdResp.not_found(msg=str(exc))
    except WorkspaceContentError as exc:
        return StdResp.error(msg=str(exc), code=400)
    except RunnerUnavailableError:
        return StdResp.error(msg="Execution service unavailable", code=503)
    return StdResp.success(data=result.model_dump(by_alias=True))


@router.post("/sessions/{session_id}/tasks/{task_id}/submit")
async def submit_task(
    session_id: int,
    task_id: str,
    payload: SubmitTaskRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    service: WorkspaceService = Depends(get_service),
):
    """提交任务：跑断言并落 TaskAttempt。"""
    try:
        result = await service.submit_task(
            visitor_id, session_id, task_id, payload.request_id
        )
    except WorkspaceNotFound as exc:
        return StdResp.not_found(msg=str(exc))
    except WorkspaceContentError as exc:
        return StdResp.error(msg=str(exc), code=400)
    except RunnerUnavailableError:
        return StdResp.error(msg="Execution service unavailable", code=503)
    return StdResp.success(data=result.model_dump(by_alias=True))