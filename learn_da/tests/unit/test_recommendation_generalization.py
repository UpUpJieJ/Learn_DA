import pytest

from app.learning.recommendation import RecommendationService
from app.learning.repository import LearningRepository


class FakeRepository:
    def __init__(self, lessons: list[dict]):
        self.lessons = lessons

    def list_lessons(self):
        return self.lessons


@pytest.mark.unit
async def test_python_track_recommends_python_successor_from_metadata():
    service = RecommendationService(repository=LearningRepository())

    result = await service.get_recommendation(
        visitor_id="python-track-user",
        completed_lessons=["python-functions"],
        current_lesson_slug="python-functions",
    )

    assert result.primary is not None
    assert result.primary.type == "next_lesson"
    assert result.primary.target_slug == "python-collections"
    assert result.primary.context["track"] == "python_basics"
    assert result.primary.context["topic"] == "programming"


@pytest.mark.unit
async def test_branch_recommendations_are_generated_from_generic_metadata():
    service = RecommendationService(
        repository=FakeRepository(
            [
                {
                    "id": 1,
                    "slug": "writing-basics",
                    "title": "写作基础",
                    "topic": "writing",
                    "category": "writing",
                    "difficulty": "beginner",
                    "order": 1,
                    "track": "writing_basics",
                    "recommended_next": ["story-writing", "essay-writing"],
                    "is_branch_point": True,
                },
                {
                    "id": 2,
                    "slug": "story-writing",
                    "title": "故事写作",
                    "topic": "writing",
                    "category": "story",
                    "difficulty": "beginner",
                    "order": 2,
                    "track": "creative_writing",
                    "prerequisites": ["writing-basics"],
                },
                {
                    "id": 3,
                    "slug": "essay-writing",
                    "title": "议论文写作",
                    "topic": "writing",
                    "category": "essay",
                    "difficulty": "beginner",
                    "order": 3,
                    "track": "essay_writing",
                    "prerequisites": ["writing-basics"],
                },
            ]
        )
    )

    result = await service.get_recommendation(
        visitor_id="generic-branch-user",
        completed_lessons=["writing-basics"],
        current_lesson_slug="writing-basics",
    )

    assert result.primary is not None
    assert result.primary.type == "branch_path"
    assert result.primary.target_slug == "story-writing"
    assert [rec.target_slug for rec in result.alternatives] == ["essay-writing"]
    assert result.primary.context["branch_point"] == "writing-basics"
    assert result.primary.context["track"] == "creative_writing"
