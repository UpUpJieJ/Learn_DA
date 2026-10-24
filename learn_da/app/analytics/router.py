"""
Phase 2 & 3 & 4 & 5: 学习行为事件采集 + 学习流优化 + 首页统计 + Dashboard API
"""

from fastapi import APIRouter, Depends, Query, Request
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



# ── Phase 3: 学习流优化 ─────────────────────────────────


@router.get("/analytics/learning-progress")
async def get_learning_progress(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户学习进度（已完成课程列表 + 各课程统计）"""
    service = AnalyticsService(db)
    result = await service.get_user_lesson_stats(visitor_id)
    return StdResp.success(data=result)


# ── Phase 4: 首页统计 ───────────────────────────────────


@router.get("/analytics/home-stats")
async def get_home_stats(
    db: AsyncSession = Depends(get_db),
):
    """获取首页展示的统计数据（总学习人数、今日活跃、代码运行次数）"""
    service = AnalyticsService(db)
    result = await service.get_home_stats()
    return StdResp.success(data=result)


# ── Phase 5: Dashboard ──────────────────────────────────


@router.get("/analytics/user-profile")
async def get_user_profile(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户画像（累计学习时长、连续天数、能力雷达图分数）"""
    service = AnalyticsService(db)
    result = await service.get_user_profile(visitor_id)
    return StdResp.success(data=result)


@router.get("/analytics/user-lesson-stats")
async def get_user_lesson_stats(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户课程维度统计"""
    service = AnalyticsService(db)
    result = await service.get_user_lesson_stats(visitor_id)
    return StdResp.success(data=result)


@router.get("/analytics/daily-trend")
async def get_daily_trend(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """获取平台每日趋势数据"""
    service = AnalyticsService(db)
    result = await service.get_daily_trend(days)
    return StdResp.success(data=result)


@router.get("/analytics/category-progress")
async def get_category_progress(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户各分类学习进度"""
    service = AnalyticsService(db)
    result = await service.get_category_progress(visitor_id)
    return StdResp.success(data=result)


