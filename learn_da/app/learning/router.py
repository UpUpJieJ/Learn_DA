from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import AnalyticsService
from app.core import get_anonymous_visitor_id
from app.core.content_loader import load_catalog
from app.core.database.database import get_db
from app.learner_state.service import LearnerStateService
from app.utils.base_response import StdResp

from .recommendation import RecommendationService
from .repository import LearningRepository
from .schemas import (
    ExampleDetail,
    ExampleSummary,
    LessonDetail,
    LessonSummary,
    RecommendationResponse,
)
from .service import LearningService

router = APIRouter(tags=["learning"])


def get_learning_service() -> LearningService:
    return LearningService(repository=LearningRepository())


def get_recommendation_service(
    db: AsyncSession = Depends(get_db),
) -> RecommendationService:
    return RecommendationService(
        repository=LearningRepository(),
        analytics_service=AnalyticsService(db),
        learner_state_service=LearnerStateService(db),
    )


@router.get("/lessons", response_model=StdResp[list[LessonSummary]])
async def list_lessons(
    topic: str | None = None,
    track: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    keyword: str | None = None,
    service: LearningService = Depends(get_learning_service),
):
    return StdResp.success(
        data=service.list_lessons(
            topic=topic,
            track=track,
            category=category,
            difficulty=difficulty,
            keyword=keyword,
        )
    )


# NOTE: /lessons/all and /lessons/categories MUST be defined BEFORE /lessons/{slug}
# to prevent "all"/"categories" being matched as a slug.


@router.get("/lessons/all", response_model=StdResp[list[LessonSummary]])
async def list_all_lessons(
    topic: str | None = None,
    track: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    keyword: str | None = None,
    service: LearningService = Depends(get_learning_service),
):
    return StdResp.success(
        data=service.list_lessons(
            topic=topic,
            track=track,
            category=category,
            difficulty=difficulty,
            keyword=keyword,
        )
    )


@router.get("/lessons/categories")
async def get_category_stats(
    service: LearningService = Depends(get_learning_service),
):
    return StdResp.success(data=service.get_category_stats())


@router.get("/catalog")
async def get_catalog():
    return StdResp.success(data=load_catalog())


@router.get("/lessons/{slug}", response_model=StdResp[LessonDetail])
async def get_lesson(
    slug: str,
    service: LearningService = Depends(get_learning_service),
):
    return StdResp.success(data=service.get_lesson(slug))


@router.get("/examples", response_model=StdResp[list[ExampleSummary]])
async def list_examples(
    service: LearningService = Depends(get_learning_service),
):
    return StdResp.success(data=service.list_examples())


@router.get("/examples/{slug}", response_model=StdResp[ExampleDetail])
async def get_example(
    slug: str,
    service: LearningService = Depends(get_learning_service),
):
    return StdResp.success(data=service.get_example(slug))


# =====================================================
# Phase 3: 学习建议接口
# =====================================================


@router.get("/recommendations", response_model=StdResp[RecommendationResponse])
async def get_recommendations(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    current_lesson: str | None = None,
    service: RecommendationService = Depends(get_recommendation_service),
    db: AsyncSession = Depends(get_db),
):
    """
    获取用户的下一步学习建议

    完成状态从服务器端 Learner State 读取，不再信任客户端自报。
    """
    result = await service.get_recommendation(
        visitor_id=visitor_id,
        current_lesson_slug=current_lesson,
    )

    # 回补建议会写入冷却记录，提交以保证跨进程 / 重启后仍然生效。
    await db.commit()
    return StdResp.success(data=result)
