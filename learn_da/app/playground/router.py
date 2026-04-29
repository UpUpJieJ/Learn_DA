from fastapi import APIRouter, Depends, Request

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

router = APIRouter(prefix="/playground", tags=["playground"])


def get_playground_service() -> PlaygroundService:
    return PlaygroundService()


@router.post("/execute", response_model=StdResp[ExecuteCodeResponse])
@limiter.limit(settings.RATE_LIMIT_PLAYGROUND_EXECUTE)
async def execute_code(
    request: Request,
    payload: ExecuteCodeRequest,
    service: PlaygroundService = Depends(get_playground_service),
):
    return StdResp.success(data=service.execute(payload))


@router.post("/format", response_model=StdResp[FormatCodeResponse])
async def format_code(
    payload: FormatCodeRequest,
    service: PlaygroundService = Depends(get_playground_service),
):
    return StdResp.success(data=service.format_code(payload))
