from fastapi import APIRouter, Depends, Request

from app.utils.base_response import StdResp
from app.utils.limiter import limiter
from config.settings import settings

from .schemas import (
    AgentChatData,
    AgentChatRequest,
    ExplainCodeRequest,
    ExplainCodeResponse,
    FixCodeRequest,
    FixCodeResponse,
)
from .service import AgentService

router = APIRouter(prefix="/agent", tags=["agent"])


def get_agent_service() -> AgentService:
    return AgentService()


@router.post("/chat", response_model=StdResp[AgentChatData])
@limiter.limit(settings.RATE_LIMIT_AGENT_CHAT)
async def chat_with_agent(
    request: Request,
    payload: AgentChatRequest,
    service: AgentService = Depends(get_agent_service),
):
    user_message = service.extract_user_message(payload)
    if not user_message:
        return StdResp.error(msg="message is required", code=422).to_response()
    return StdResp.success(data=await service.chat(payload))


@router.post("/fix", response_model=StdResp[FixCodeResponse])
@limiter.limit(settings.RATE_LIMIT_AGENT_CHAT)
async def fix_code(
    request: Request,
    payload: FixCodeRequest,
    service: AgentService = Depends(get_agent_service),
):
    return StdResp.success(data=await service.fix_code(payload))


@router.post("/explain", response_model=StdResp[ExplainCodeResponse])
@limiter.limit(settings.RATE_LIMIT_AGENT_CHAT)
async def explain_code(
    request: Request,
    payload: ExplainCodeRequest,
    service: AgentService = Depends(get_agent_service),
):
    return StdResp.success(data=await service.explain_code(payload))
