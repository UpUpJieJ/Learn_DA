from fastapi import APIRouter, Depends

from app.utils.base_response import StdResp

from .repository import LearningRepository
from .schemas import ExampleDetail, ExampleSummary, LessonDetail, LessonSummary
from .service import LearningService

router = APIRouter(tags=["learning"])


def get_learning_service() -> LearningService:
    return LearningService(repository=LearningRepository())


@router.get("/lessons", response_model=StdResp[list[LessonSummary]])
async def list_lessons(
    category: str | None = None,
    difficulty: str | None = None,
    keyword: str | None = None,
    service: LearningService = Depends(get_learning_service),
):
    return StdResp.success(
        data=service.list_lessons(
            category=category,
            difficulty=difficulty,
            keyword=keyword,
        )
    )


# NOTE: /lessons/all and /lessons/categories MUST be defined BEFORE /lessons/{slug}
# to prevent "all"/"categories" being matched as a slug.

@router.get("/lessons/all", response_model=StdResp[list[LessonSummary]])
async def list_all_lessons(
    category: str | None = None,
    difficulty: str | None = None,
    keyword: str | None = None,
    service: LearningService = Depends(get_learning_service),
):
    return StdResp.success(
        data=service.list_lessons(
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
