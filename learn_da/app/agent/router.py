from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import EventTrackRequest, EventType
from app.analytics.service import AnalyticsService
from app.core import get_anonymous_visitor_id
from app.core.database.database import get_db
from app.learning.recommendation import RecommendationService
from app.learning.repository import LearningRepository
from app.learner_state.service import LearnerStateService
from app.utils import log
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
    RecommendationGuidanceRequest,
    RecommendationGuidanceResponse,
)
from .service import AgentService

router = APIRouter(prefix="/agent", tags=["agent"])


def get_agent_service(
    db: AsyncSession = Depends(get_db),
) -> AgentService:
    return AgentService(
        analytics_service=AnalyticsService(db),
        learner_state_service=LearnerStateService(db),
    )


def get_recommendation_guidance_service(
    db: AsyncSession = Depends(get_db),
) -> AgentService:
    learner_state = LearnerStateService(db)
    return AgentService(
        recommendation_service=RecommendationService(
            repository=LearningRepository(),
            analytics_service=AnalyticsService(db),
            learner_state_service=learner_state,
        ),
        learner_state_service=learner_state,
        analytics_service=AnalyticsService(db),
    )


@router.post("/chat", response_model=StdResp[AgentChatData])
@limiter.limit(settings.RATE_LIMIT_AGENT_CHAT)
async def chat_with_agent(
    request: Request,
    payload: AgentChatRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    service: AgentService = Depends(get_agent_service),
):
    user_message = service.extract_user_message(payload)
    if not user_message:
        return StdResp.error(msg="message is required", code=422).to_response()
    data = await service.chat(payload)

    # 阶段 1：Agent 后端成功受理后记录 ai_help 事件，统一学习事实来源。
    # event_id 关联当前请求 ID，同一请求重放不会重复写入。
    #
    # 埋点是旁路副作用：LLM 调用已经发生（且已计费），此处失败绝不能把一次成功的
    # 回答变成 500，因此吞掉异常只记日志。
    if service.analytics_service is not None:
        from app.utils.logger import request_id_var

        req_id = request_id_var.get()
        try:
            await service.analytics_service.track_event(
                EventTrackRequest.model_validate(
                    {
                        "eventType": EventType.AI_HELP.value,
                        "lessonSlug": (
                            payload.context.current_lesson if payload.context else None
                        ),
                        "eventId": f"ai_help:{visitor_id}:{req_id}",
                    }
                ),
                visitor_id=visitor_id,
            )
        except Exception:
            log.exception("[agent] ai_help 埋点写入失败，已忽略以保全聊天响应")

    return StdResp.success(data=data)


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


@router.post(
    "/recommendation-guidance",
    response_model=StdResp[RecommendationGuidanceResponse],
)
@limiter.limit(settings.RATE_LIMIT_AGENT_CHAT)
async def recommendation_guidance(
    request: Request,
    payload: RecommendationGuidanceRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    service: AgentService = Depends(get_recommendation_guidance_service),
):
    return StdResp.success(
        data=await service.recommendation_guidance(payload, visitor_id=visitor_id)
    )
