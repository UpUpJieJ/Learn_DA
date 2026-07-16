import logging

from fastapi import APIRouter, Depends, Request, Response

from app.sandbox import RunnerUnavailableError
from app.sandbox.schemas import ExecutionStatus
from app.utils.base_response import StdResp
from app.utils.limiter import limiter
from config.settings import settings

from .schemas import (
    ExecuteCodeRequest,
    ExecuteCodeResponse,
    FormatCodeRequest,
    FormatCodeResponse,
)
from .service import PlaygroundService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/playground", tags=["playground"])


def get_playground_service(request: Request) -> PlaygroundService:
    runner_client = request.app.state.runner_client
    from app.sandbox import SandboxService

    return PlaygroundService(sandbox_service=SandboxService(runner_client=runner_client))


@router.post("/execute")
@limiter.limit(settings.RATE_LIMIT_PLAYGROUND_EXECUTE)
async def execute_code(
    request: Request,
    payload: ExecuteCodeRequest,
    service: PlaygroundService = Depends(get_playground_service),
):
    try:
        result = await service.execute(payload)
        return StdResp.success(data=result.model_dump(by_alias=True))
    except RunnerUnavailableError:
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
            data=unavailable.model_dump(by_alias=True),
        ).to_response()


@router.post("/format", response_model=StdResp[FormatCodeResponse])
async def format_code(
    payload: FormatCodeRequest,
    service: PlaygroundService = Depends(get_playground_service),
):
    return StdResp.success(data=service.format_code(payload))
