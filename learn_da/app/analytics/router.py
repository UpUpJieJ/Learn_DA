"""
学习事件采集：所有学习事实复用相同的幂等服务入口。旧 Dashboard GET 已下线。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db, get_anonymous_visitor_id
from app.utils.base_response import StdResp
from app.utils.limiter import limiter
from config.settings import settings

from .schemas import (
    EventTrackRequest,
    EventTrackResponse,
)
from .service import AnalyticsService

router = APIRouter(tags=["analytics"])


# ── Phase 2: 事件采集 ───────────────────────────────────


@router.post("/analytics/track", response_model=StdResp[EventTrackResponse])
@limiter.limit(settings.RATE_LIMIT_ANALYTICS_WRITE)
async def track_event(
    request: Request,
    req: EventTrackRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """记录学习行为事件"""
    service = AnalyticsService(db)
    result = await service.track_event(req, visitor_id)
    return StdResp.success(data=result)
