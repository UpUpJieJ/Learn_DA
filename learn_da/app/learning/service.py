from typing import Any

from fastapi import status

from app.core.exceptions.base_exceptions import BusinessException

from .repository import LearningRepository
from .schemas import ExampleDetail, ExampleSummary, LessonDetail, LessonSummary


class LearningService:
    def __init__(self, repository: LearningRepository | None = None):
        self.repository = repository or LearningRepository()

    def list_lessons(
        self,
        category: str | None = None,
        difficulty: str | None = None,
        keyword: str | None = None,
    ) -> list[LessonSummary]:
        return [
            LessonSummary.model_validate(lesson)
            for lesson in self.repository.list_lessons(
                category=category,
                difficulty=difficulty,
                keyword=keyword,
            )
        ]

    def get_lesson(self, slug: str) -> LessonDetail:
        lesson = self.repository.get_lesson(slug)
        if lesson is None:
            raise BusinessException(
                message=f"lesson '{slug}' not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return lesson

    def list_examples(self) -> list[ExampleSummary]:
        return [
            ExampleSummary.model_validate(example)
            for example in self.repository.list_examples()
        ]

    def get_example(self, slug: str) -> ExampleDetail:
        example = self.repository.get_example(slug)
        if example is None:
            raise BusinessException(
                message=f"example '{slug}' not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return example

    def get_category_stats(self) -> list[dict[str, Any]]:
        return self.repository.get_category_stats()
