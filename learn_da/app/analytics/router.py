"""
Phase 2 & 3 & 4 & 5: 学习行为事件采集 + 学习流优化 + 首页统计 + Dashboard API
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.learning.repository import LearningRepository
from app.utils.base_response import StdResp

from .schemas import (
    CodeSnapshotItem,
    CodeSnapshotRequest,
    CodeSnapshotResponse,
    EventTrackRequest,
    EventTrackResponse,
)
from .service import AnalyticsService

router = APIRouter(tags=["analytics"])


# ── Phase 2: 事件采集 ───────────────────────────────────


@router.post("/analytics/track", response_model=StdResp[EventTrackResponse])
async def track_event(
    req: EventTrackRequest,
    db: AsyncSession = Depends(get_db),
):
    """记录学习行为事件"""
    service = AnalyticsService(db)
    result = await service.track_event(req)
    return StdResp.success(data=result)


@router.post("/analytics/snapshot", response_model=StdResp[CodeSnapshotResponse])
async def save_snapshot(
    req: CodeSnapshotRequest,
    db: AsyncSession = Depends(get_db),
):
    """保存代码快照"""
    service = AnalyticsService(db)
    result = await service.save_snapshot(req)
    return StdResp.success(data=result)


@router.get("/analytics/snapshots", response_model=StdResp[list[CodeSnapshotItem]])
async def list_snapshots(
    visitor_id: str = Query(..., alias="visitorId"),
    lesson_slug: str | None = Query(None, alias="lessonSlug"),
    db: AsyncSession = Depends(get_db),
):
    """获取代码快照列表"""
    service = AnalyticsService(db)
    result = await service.list_snapshots(visitor_id, lesson_slug)
    return StdResp.success(data=result)


# ── Phase 3: 学习流优化 ─────────────────────────────────


@router.get("/analytics/learning-progress")
async def get_learning_progress(
    visitor_id: str = Query(..., alias="visitorId"),
    db: AsyncSession = Depends(get_db),
):
    """获取用户学习进度（已完成课程列表 + 各课程统计）"""
    service = AnalyticsService(db)
    result = await service.get_user_lesson_stats(visitor_id)
    return StdResp.success(data=result)


@router.get("/analytics/recommended-lessons")
async def get_recommended_lessons(
    visitor_id: str = Query(..., alias="visitorId"),
    db: AsyncSession = Depends(get_db),
):
    """基于用户进度推荐下一节课"""
    service = AnalyticsService(db)
    repo = LearningRepository()

    # 获取用户已完成的课程
    lesson_stats = await service.get_user_lesson_stats(visitor_id)
    completed_slugs = set(lesson_stats.get("completedLessons", []))

    # 获取全部课程
    all_lessons = repo.list_lessons()
    all_lessons.sort(key=lambda x: x.order)

    # 推荐逻辑：找第一个未完成的课程
    recommended = None
    for lesson in all_lessons:
        if lesson.slug not in completed_slugs:
            recommended = {
                "slug": lesson.slug,
                "title": lesson.title,
                "description": lesson.description,
                "category": lesson.category,
                "difficulty": lesson.difficulty,
                "estimatedMinutes": lesson.estimated_minutes,
                "order": lesson.order,
                "tags": lesson.tags,
            }
            break

    # 如果全部完成，推荐第一个课程（重学）
    if recommended is None and all_lessons:
        first = all_lessons[0]
        recommended = {
            "slug": first.slug,
            "title": first.title,
            "description": first.description,
            "category": first.category,
            "difficulty": first.difficulty,
            "estimatedMinutes": first.estimated_minutes,
            "order": first.order,
            "tags": first.tags,
        }

    return StdResp.success(data={
        "recommended": recommended,
        "completedCount": len(completed_slugs),
        "totalCount": len(all_lessons),
    })


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
    visitor_id: str = Query(..., alias="visitorId"),
    db: AsyncSession = Depends(get_db),
):
    """获取用户画像（累计学习时长、连续天数、能力雷达图分数）"""
    service = AnalyticsService(db)
    result = await service.get_user_profile(visitor_id)
    return StdResp.success(data=result)


@router.get("/analytics/user-lesson-stats")
async def get_user_lesson_stats(
    visitor_id: str = Query(..., alias="visitorId"),
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
    visitor_id: str = Query(..., alias="visitorId"),
    db: AsyncSession = Depends(get_db),
):
    """获取用户各分类学习进度"""
    service = AnalyticsService(db)
    result = await service.get_category_progress(visitor_id)
    return StdResp.success(data=result)
