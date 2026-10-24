import logging

from fastapi import APIRouter, Depends, Request

from app.core.session import get_anonymous_visitor_id
from app.sandbox import RunnerUnavailableError, SandboxService
from app.sandbox.schemas import ExecutionStatus
from app.utils.base_response import StdResp
from app.utils.limiter import limiter
from config.settings import settings

from .schemas import ExecuteCodeRequest, ExecuteCodeResponse
from .service import PlaygroundService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/playground", tags=["playground"])


def get_playground_service(request: Request) -> PlaygroundService:
    runner_client = request.app.state.runner_client
    return PlaygroundService(
        sandbox_service=SandboxService(runner_client=runner_client)
    )


@router.post("/execute")
@limiter.limit(settings.RATE_LIMIT_PLAYGROUND_EXECUTE)
async def execute_code(
    request: Request,
    payload: ExecuteCodeRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
):
    """执行代码（自由沙盒；练习判定走 ``/workspace`` 任务提交）。"""
    try:
        service = get_playground_service(request)
        result = await service.execute(payload)
        return StdResp.success(data=result.model_dump(by_alias=True))
    except RunnerUnavailableError:
        return _runner_unavailable_response(payload)


def _runner_unavailable_response(payload: ExecuteCodeRequest):
    log.warning("Runner unavailable during playground execution")
    unavailable = ExecuteCodeResponse(
        request_id=payload.request_id,
        status=ExecutionStatus.UNAVAILABLE,
        stdout="",
        stderr="",
        error_type="runner_unavailable",
        duration_ms=0,
    )
    return StdResp.error(
        msg="Execution service unavailable",
        code=503,
        data=unavailable.model_dump(mode="json", by_alias=True),
    ).to_response()
