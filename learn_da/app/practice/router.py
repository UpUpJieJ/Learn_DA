"""
Phase 2: 可验证练习闭环 - Practice Router

- GET  /playground/exercises/{exercise_id}/resume  恢复练习
- GET  /playground/exercises/{exercise_id}/attempts  尝试列表
- GET  /playground/exercises/{exercise_id}/stats    练习统计
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.database import get_db
from app.core.session import get_anonymous_visitor_id
from app.utils.base_response import StdResp

from .repository import PracticeRepository
from .service import PracticeService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/playground", tags=["practice"])


@router.get("/exercises/{exercise_id}/resume")
async def resume_exercise(
    exercise_id: str,
    lesson_slug: str = Query(..., alias="lessonSlug", description="课程 slug"),
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """恢复练习：返回最近未通过尝试的代码，或 starter code"""
    repo = PracticeRepository(db)
    service = PracticeService(db=db, practice_repo=repo)
    result = await service.get_resume_data(visitor_id, lesson_slug, exercise_id)
    if result is None:
        return StdResp.not_found(
            msg=f"练习 '{exercise_id}' 不存在于课程 '{lesson_slug}'"
        )
    return StdResp.success(data=result.model_dump(by_alias=True))


@router.get("/exercises/{exercise_id}/attempts")
async def list_exercise_attempts(
    exercise_id: str,
    lesson_slug: str = Query(..., alias="lessonSlug", description="课程 slug"),
    limit: int = Query(20, ge=1, le=50),
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取某练习的尝试列表"""
    repo = PracticeRepository(db)
    service = PracticeService(db=db, practice_repo=repo)
    if service.get_exercise_definition(lesson_slug, exercise_id) is None:
        return StdResp.not_found(
            msg=f"练习 '{exercise_id}' 不存在于课程 '{lesson_slug}'"
        )
    summaries = await service.get_attempt_summaries(
        visitor_id,
        lesson_slug,
        limit,
        exercise_id=exercise_id,
    )
    return StdResp.success(data=[s.model_dump(by_alias=True) for s in summaries])


@router.get("/exercises/{exercise_id}/stats")
async def get_exercise_stats(
    exercise_id: str,
    lesson_slug: str = Query(..., alias="lessonSlug", description="课程 slug"),
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取某练习的统计信息"""
    repo = PracticeRepository(db)
    service = PracticeService(db=db, practice_repo=repo)
    if service.get_exercise_definition(lesson_slug, exercise_id) is None:
        return StdResp.not_found(
            msg=f"练习 '{exercise_id}' 不存在于课程 '{lesson_slug}'"
        )
    stats = await service.get_exercise_stats(visitor_id, exercise_id)
    return StdResp.success(data=stats)
