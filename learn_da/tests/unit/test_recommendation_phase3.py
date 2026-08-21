from datetime import datetime, timedelta, timezone

import pytest

from app.analytics.models import LearningRecord, UserProfile
from app.learning.recommendation import RecommendationService
from config.settings import Settings


class FakeRepository:
    def __init__(self, lessons: list[dict]):
        self.lessons = lessons

    def list_lessons(self):
        return self.lessons


class FakeAnalyticsService:
    def __init__(
        self,
        *,
        profile: dict | None = None,
        stats_by_lesson: dict[str, dict] | None = None,
        incomplete_lessons: list[dict] | None = None,
    ):
        self.profile = profile or {}
        self.stats_by_lesson = stats_by_lesson or {}
        self.incomplete_lessons = incomplete_lessons or []

    async def get_lesson_specific_stats(self, visitor_id: str, lesson_slug: str):
        return self.stats_by_lesson.get(
            lesson_slug,
            {"codeRuns": 0, "aiHelps": 0, "completed": False},
        )

    async def get_user_profile(self, visitor_id: str):
        return self.profile

    async def get_incomplete_lessons_with_activity(
        self,
        visitor_id: str,
        completed_lessons: list[str],
    ):
        return self.incomplete_lessons


class FakeLearnerStateService:
    """内存版冷却管理，用于测试阶段 1 持久化冷却。"""

    def __init__(self):
        self._cooldowns: dict[str, datetime] = {}

    async def is_in_cooldown(self, visitor_id: str, lesson_slug: str) -> bool:
        key = f"{visitor_id}:{lesson_slug}"
        until = self._cooldowns.get(key)
        if until is None:
            return False
        return datetime.now(timezone.utc) < until

    async def set_cooldown(
        self, visitor_id: str, lesson_slug: str, seconds: int
    ) -> None:
        key = f"{visitor_id}:{lesson_slug}"
        self._cooldowns[key] = datetime.now(timezone.utc) + timedelta(seconds=seconds)

    async def get_completed_lessons(self, visitor_id: str) -> list[str]:
        return []


def recommendation_lessons() -> list[dict]:
    return [
        {
            "slug": "intro",
            "title": "基础入门",
            "topic": "programming",
            "category": "python",
            "difficulty": "beginner",
            "order": 1,
            "track": "python_basics",
            "recommended_next": ["current"],
            "skill_tags": ["function", "loop"],
            "is_review_friendly": True,
        },
        {
            "slug": "current",
            "title": "当前练习",
            "topic": "programming",
            "category": "python",
            "difficulty": "intermediate",
            "order": 2,
            "track": "python_basics",
            "prerequisites": ["intro"],
            "skill_tags": ["function", "loop", "list"],
        },
    ]


@pytest.mark.unit
async def test_review_recommendation_triggers_on_code_runs_and_cools_down():
    analytics = FakeAnalyticsService(
        stats_by_lesson={
            "current": {"codeRuns": 5, "aiHelps": 0, "completed": False},
        }
    )
    learner_state = FakeLearnerStateService()
    service = RecommendationService(
        repository=FakeRepository(recommendation_lessons()),
        analytics_service=analytics,
        learner_state_service=learner_state,
    )

    first = await service.get_recommendation(
        visitor_id="review-user",
        completed_lessons=["intro"],
        current_lesson_slug="current",
    )
    second = await service.get_recommendation(
        visitor_id="review-user",
        completed_lessons=["intro"],
        current_lesson_slug="current",
    )

    assert first.primary is not None
    assert first.primary.type == "review_lesson"
    assert first.primary.target_slug == "intro"
    assert first.primary.priority == 5
    assert first.primary.context["code_runs"] == 5
    assert second.primary is None


def test_recommendation_thresholds_are_available_in_settings():
    settings = Settings(
        CORS_ORIGINS="http://test",
        RECOMMENDATION_CODE_RUNS_THRESHOLD=2,
        RECOMMENDATION_AI_HELPS_THRESHOLD=2,
        RECOMMENDATION_REVIEW_COOLDOWN_SECONDS=60,
        RECOMMENDATION_RESUME_ABSENCE_THRESHOLD_DAYS=9,
    )

    assert settings.RECOMMENDATION_CODE_RUNS_THRESHOLD == 2
    assert settings.RECOMMENDATION_AI_HELPS_THRESHOLD == 2
    assert settings.RECOMMENDATION_REVIEW_COOLDOWN_SECONDS == 60
    assert settings.RECOMMENDATION_RESUME_ABSENCE_THRESHOLD_DAYS == 9


@pytest.mark.unit
async def test_recommendation_service_uses_configured_code_run_threshold(monkeypatch):
    import app.learning.recommendation as recommendation_module

    monkeypatch.setattr(
        recommendation_module.settings,
        "RECOMMENDATION_CODE_RUNS_THRESHOLD",
        2,
    )
    analytics = FakeAnalyticsService(
        stats_by_lesson={
            "current": {"codeRuns": 2, "aiHelps": 0, "completed": False},
        }
    )
    service = recommendation_module.RecommendationService(
        repository=FakeRepository(recommendation_lessons()),
        analytics_service=analytics,
    )

    result = await service.get_recommendation(
        visitor_id="configured-review-user",
        completed_lessons=["intro"],
        current_lesson_slug="current",
    )

    assert result.primary is not None
    assert result.primary.type == "review_lesson"
    assert result.primary.target_slug == "intro"


@pytest.mark.unit
async def test_configured_branch_recommendations_prioritize_met_prerequisites():
    service = RecommendationService(
        repository=FakeRepository(
            [
                {
                    "slug": "duckdb-analytics",
                    "title": "DuckDB 基础分析",
                    "topic": "data-analysis",
                    "category": "duckdb",
                    "difficulty": "beginner",
                    "order": 1,
                    "track": "duckdb_basics",
                },
                {
                    "slug": "polars-groupby",
                    "title": "Polars 分组聚合",
                    "topic": "data-analysis",
                    "category": "polars",
                    "difficulty": "intermediate",
                    "order": 2,
                    "track": "polars_basics",
                },
                {
                    "slug": "polars-expressions",
                    "title": "Polars 表达式",
                    "topic": "data-analysis",
                    "category": "polars",
                    "difficulty": "intermediate",
                    "order": 3,
                    "track": "polars_basics",
                },
                {
                    "slug": "polars-joins",
                    "title": "Polars 连接",
                    "topic": "data-analysis",
                    "category": "polars",
                    "difficulty": "intermediate",
                    "order": 4,
                    "track": "polars_basics",
                    "recommended_next": [
                        "duckdb-sql-foundations",
                        "polars-lazy-pipeline",
                    ],
                    "is_branch_point": True,
                },
                {
                    "slug": "duckdb-sql-foundations",
                    "title": "DuckDB SQL 基础",
                    "topic": "data-analysis",
                    "category": "duckdb",
                    "difficulty": "beginner",
                    "order": 5,
                    "track": "duckdb_basics",
                },
                {
                    "slug": "polars-lazy-pipeline",
                    "title": "Polars 惰性流水线",
                    "topic": "data-analysis",
                    "category": "polars",
                    "difficulty": "advanced",
                    "order": 6,
                    "track": "polars_advanced",
                },
            ]
        )
    )

    result = await service.get_recommendation(
        visitor_id="branch-user",
        completed_lessons=["duckdb-analytics", "polars-joins"],
        current_lesson_slug="polars-joins",
    )

    assert result.primary is not None
    assert result.primary.type == "branch_path"
    assert result.primary.target_slug == "duckdb-sql-foundations"
    assert result.primary.priority == 4
    assert result.alternatives[0].target_slug == "polars-lazy-pipeline"
    assert result.alternatives[0].priority == 3


@pytest.mark.unit
async def test_resume_recommendation_selects_lowest_resume_cost():
    today = datetime.now(timezone.utc).date()
    analytics = FakeAnalyticsService(
        profile={"lastActiveDate": (today - timedelta(days=10)).strftime("%Y-%m-%d")},
        incomplete_lessons=[
            {
                "lesson_slug": "intro",
                "code_runs": 1,
                "ai_helps": 0,
                "last_activity_time": datetime.now(timezone.utc) - timedelta(days=1),
            },
            {
                "lesson_slug": "current",
                "code_runs": 10,
                "ai_helps": 2,
                "last_activity_time": datetime.now(timezone.utc) - timedelta(days=8),
            },
        ],
    )
    service = RecommendationService(
        repository=FakeRepository(recommendation_lessons()),
        analytics_service=analytics,
    )

    result = await service.get_recommendation(
        visitor_id="resume-user",
        completed_lessons=[],
    )

    assert result.primary is not None
    assert result.primary.type == "resume_session"
    assert result.primary.target_slug == "current"
    assert result.primary.context["resume_cost"] < 50


@pytest.mark.unit
async def test_recommendations_endpoint_uses_tracked_events_for_review(test_engine):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core import get_anonymous_visitor_id
    from app.core.database.database import get_db
    from main import app

    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    session = async_session()

    async def override_get_db():
        yield session

    visitor_id = "analytics-review-user"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_anonymous_visitor_id] = lambda: visitor_id
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as api_client:
            for _ in range(5):
                resp = await api_client.post(
                    "/api/v1/analytics/track",
                    json={
                        "eventType": "code_run",
                        "lessonSlug": "polars-expressions",
                    },
                )
                assert resp.status_code == 200

            resp = await api_client.get(
                "/api/v1/recommendations",
                params={
                    "completed_lessons": "polars-basics",
                    "current_lesson": "polars-expressions",
                },
            )
    finally:
        app.dependency_overrides.clear()
        await session.close()

    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["primary"]["type"] == "review_lesson"
    assert body["data"]["primary"]["targetSlug"] == "polars-basics"


@pytest.mark.unit
async def test_recommendations_endpoint_uses_real_analytics_for_resume(
    client, db_session
):
    visitor_id = "analytics-resume-user"
    today = datetime.now(timezone.utc).date()
    db_session.add(
        UserProfile(
            visitor_id=visitor_id,
            last_active_date=(today - timedelta(days=10)).strftime("%Y-%m-%d"),
        )
    )
    db_session.add_all(
        [
            LearningRecord(
                visitor_id=visitor_id,
                event_type="code_run",
                lesson_slug="polars-expressions",
                created_time=datetime.now(timezone.utc) - timedelta(days=4),
            )
            for _ in range(6)
        ]
    )
    await db_session.flush()

    from app.core import get_anonymous_visitor_id
    from main import app

    visitor_id = "analytics-resume-user"
    app.dependency_overrides[get_anonymous_visitor_id] = lambda: visitor_id
    try:
        resp = await client.get(
            "/api/v1/recommendations",
            params={
                "completed_lessons": "polars-basics",
            },
        )
    finally:
        app.dependency_overrides.clear()
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["primary"]["type"] == "resume_session"
    assert body["data"]["primary"]["targetSlug"] == "polars-expressions"
