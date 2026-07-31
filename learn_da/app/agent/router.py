from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import EventTrackRequest, EventType
from app.analytics.service import AnalyticsService
from app.core import get_anonymous_visitor_id
from app.core.database.database import get_db
from app.learner_state.service import LearnerStateService
from app.utils import log
from app.utils.base_response import StdResp
from app.utils.limiter import limiter
from config.settings import settings

from .knowledge import KnowledgeRetriever
from .schemas import AgentChatData, AgentChatRequest
from .service import AgentService

router = APIRouter(prefix="/agent", tags=["agent"])


def _fc_enabled() -> bool:
    """FC 路径开关：flag 开启且有 key 才走 FC，否则保持阶段 ③ 旧路径。"""
    return bool(settings.AGENT_FC_ENABLED and settings.effective_llm_api_key)


def get_knowledge_retriever(request: Request) -> KnowledgeRetriever:
    """从应用生命周期获取共享 retriever。

    正常运行时由 lifespan 创建；未经 lifespan 的场景（如测试 ASGITransport）
    惰性创建一次并缓存到 app.state，语义与单例一致。
    """
    retriever = getattr(request.app.state, "knowledge_retriever", None)
    if retriever is None:
        retriever = KnowledgeRetriever()
        request.app.state.knowledge_retriever = retriever
    return retriever


def get_agent_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
    knowledge_retriever: KnowledgeRetriever = Depends(get_knowledge_retriever),
) -> AgentService:
    # Phase 2: 练习服务（只读摘要）
    from app.practice.repository import PracticeRepository
    from app.practice.service import PracticeService

    practice_repo = PracticeRepository(db)
    practice_service = PracticeService(db=db, practice_repo=practice_repo)

    return AgentService(
        knowledge_retriever=knowledge_retriever,
        analytics_service=AnalyticsService(db),
        learner_state_service=LearnerStateService(db),
        practice_service=practice_service,
        # lifespan 共享的 LLM client；为 None 时（无 key / 未经 lifespan 的测试）
        # 由 _complete 自建临时 client 并负责关闭。
        llm_client=getattr(request.app.state, "agent_llm_client", None),
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
    # 阶段 ④：按 flag 分流，FC 路径 / 旧关键词路由路径（降级保留）
    if _fc_enabled():
        data = await service.chat_with_tools(payload, visitor_id=visitor_id)
    else:
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
