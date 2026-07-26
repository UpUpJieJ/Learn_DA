"""
阶段 1：统一学习事实 - HTTP 接口

本模块只暴露**读**接口。状态变更统一走 `/analytics/track` 事件上报，
由 `AnalyticsService.track_event` 在同一事务内联动 `LearnerStateService`，
保证事件日志与状态投影不会分裂成两条写路径。

身份遵循阶段 0 签名匿名 session 约定，visitor_id 从 session cookie 注入，
不接受请求体或查询参数自报。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_anonymous_visitor_id, get_db
from app.utils.base_response import StdResp
from app.utils.limiter import limiter
from config.settings import settings

from .schemas import LearnerProgressSummary
from .service import LearnerStateService

router = APIRouter(tags=["learner-state"])


@router.get("/learner-state/progress", response_model=StdResp[LearnerProgressSummary])
@limiter.limit(settings.RATE_LIMIT_ANALYTICS_READ)
async def get_progress(
    request: Request,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取学习者完整进度投影（完成列表、最近位置、各课统计）"""
    service = LearnerStateService(db)
    result = await service.get_full_progress(visitor_id)
    return StdResp.success(data=result)
