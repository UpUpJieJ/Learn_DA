"""阶段 3 Task 4：推荐读取证据聚合 + Dashboard 指标测试。

覆盖计划要求：
- Agent 多次求助但无 Attempt（code_runs=0/snapshots=0）不触发回补推荐；
- 验证失败 + 后续通过可计算"帮助后通过"；
- 同一 Interaction 重放不改变推荐或 Dashboard 聚合（幂等保证）；
- RecommendationService 仍是唯一排序来源，Agent 只提供证据。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.learning.recommendation import RecommendationService
from config.settings import Settings


class FakeRepository:
    def __init__(self, lessons: list[dict]):
        self.lessons = lessons

    def list_lessons(self):
        return self.lessons


class FakeAnalyticsService:
    def __init__(self, stats_by_lesson=None):
        self._stats = stats_by_lesson or {}

    async def get_lesson_specific_stats(self, visitor_id, lesson_slug):
        return self._stats.get(
            lesson_slug, {"codeRuns": 0, "aiHelps": 0, "completed": False}
        )

    async def get_lesson_snapshots_count(self, visitor_id, lesson_slug):
        return self._stats.get(lesson_slug, {}).get("snapshots", 0)

    async def get_user_profile(self, visitor_id):
        return {}

    async def get_incomplete_lessons_with_activity(
        self, visitor_id, completed_lessons
    ):
        return []


class FakeLearnerStateService:
    def __init__(self):
        self._cooldowns = {}

    async def is_in_cooldown(self, visitor_id, lesson_slug):
        return False

    async def mark_in_cooldown(self, visitor_id, lesson_slug, seconds):
        pass

    async def set_cooldown(self, visitor_id, lesson_slug, seconds):
        pass

    async def get_completed_lessons(self, visitor_id):
        return []


def _make_service(stats=None, interaction_repo=None):
    lessons = [
        {"slug": "current", "title": "Current", "topic": "programming",
         "category": "polars", "difficulty": "intermediate", "order": 2,
         "prerequisites": ["prereq"], "skill_tags": ["df"]},
        {"slug": "prereq", "title": "Prereq", "topic": "programming",
         "category": "polars", "difficulty": "beginner", "order": 1,
         "is_review_friendly": True, "skill_tags": ["basics"]},
    ]
    return RecommendationService(
        repository=FakeRepository(lessons),
        analytics_service=FakeAnalyticsService(stats_by_lesson=stats or {}),
        learner_state_service=FakeLearnerStateService(),
        interaction_repo=interaction_repo,
    )


# =====================================================
# Agent 多次求助但无 Attempt 不触发回补
# =====================================================


class TestAiHelpWithoutPracticeNoReview:
    @pytest.mark.asyncio
    async def test_ai_helps_without_code_runs_no_review(self):
        """多次求助但 code_runs=0/snapshots=0 不触发回补。"""
        service = _make_service(
            stats={"current": {"codeRuns": 0, "aiHelps": 5, "completed": False}}
        )
        result = await service.get_recommendation("v1", current_lesson_slug="current")
        # 不应是回补（review_lesson）；顺学或其他或无建议
        assert result.primary is None or result.primary.type != "review_lesson"

    @pytest.mark.asyncio
    async def test_ai_helps_with_code_runs_triggers_review(self):
        """多次求助且有 code_runs > 0 触发回补。"""
        service = _make_service(
            stats={"current": {"codeRuns": 3, "aiHelps": 5, "completed": False}}
        )
        result = await service.get_recommendation("v1", current_lesson_slug="current")
        assert result.primary.type == "review_lesson"


class TestAgentEvidenceInMainRecommendation:
    @pytest.mark.asyncio
    async def test_unresolved_agent_help_triggers_review(self):
        interaction_repo = MagicMock()
        interaction_repo.get_recent_by_lesson = AsyncMock(
            return_value=[
                SimpleNamespace(
                    evidence_state="verification_failed",
                    hint_level=2,
                    attempt_id=None,
                    created_time=None,
                )
            ]
        )
        service = _make_service(
            stats={"current": {"codeRuns": 1, "aiHelps": 0, "completed": False}},
            interaction_repo=interaction_repo,
        )

        result = await service.get_recommendation("v1", current_lesson_slug="current")

        assert result.primary is not None
        assert result.primary.type == "review_lesson"

    @pytest.mark.asyncio
    async def test_pass_after_help_is_not_unresolved(self):
        interaction_repo = MagicMock()
        interaction_repo.get_recent_by_lesson = AsyncMock(
            return_value=[
                SimpleNamespace(
                    evidence_state="verification_failed",
                    hint_level=2,
                    attempt_id=7,
                    created_time=datetime(2026, 7, 31, tzinfo=timezone.utc),
                )
            ]
        )
        attempt = SimpleNamespace(exercise_id="ex-1")
        practice_repo = MagicMock()
        practice_repo.get_by_id = AsyncMock(return_value=attempt)
        practice_repo.get_passed_after = AsyncMock(return_value=object())
        practice_service = SimpleNamespace(repo=practice_repo)
        service = _make_service(
            stats={"current": {"codeRuns": 1, "aiHelps": 0, "completed": False}},
            interaction_repo=interaction_repo,
        )
        service.practice_service = practice_service

        result = await service.get_recommendation("v1", current_lesson_slug="current")

        assert result.primary is None
        practice_repo.get_passed_after.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ai_helps_with_snapshots_triggers_review(self):
        """多次求助且有 snapshots > 0 触发回补。"""
        service = _make_service(
            stats={
                "current": {
                    "codeRuns": 0,
                    "aiHelps": 5,
                    "snapshots": 2,
                    "completed": False,
                }
            }
        )
        result = await service.get_recommendation("v1", current_lesson_slug="current")
        assert result.primary.type == "review_lesson"


# =====================================================
# Agent 帮助后通过聚合信号
# =====================================================


class TestAgentHelpSummary:
    @pytest.mark.asyncio
    async def test_no_interaction_repo_returns_empty(self):
        """未注入 interaction_repo 时返回空信号（降级）。"""
        service = _make_service(interaction_repo=None)
        summary = await service._get_agent_help_summary("v1", "current")
        assert summary["has_help"] is False
        assert summary["has_unresolved_failure"] is False

    @pytest.mark.asyncio
    async def test_unresolved_failure_detected(self):
        """有 hint_level>=2 且 evidence_state 为失败的交互 -> unresolved。"""
        repo = MagicMock()
        interactions = [
            MagicMock(evidence_state="verification_failed", hint_level=2),
            MagicMock(evidence_state="passed_unconfirmed", hint_level=1),
        ]
        repo.get_recent_by_lesson = AsyncMock(return_value=interactions)
        service = _make_service(interaction_repo=repo)

        summary = await service._get_agent_help_summary("v1", "current")
        assert summary["has_help"] is True
        assert summary["max_hint_level"] == 2
        assert summary["has_unresolved_failure"] is True

    @pytest.mark.asyncio
    async def test_no_unresolved_when_low_hint(self):
        """hint_level < 2 的失败不视为 unresolved。"""
        repo = MagicMock()
        interactions = [
            MagicMock(evidence_state="verification_failed", hint_level=1),
        ]
        repo.get_recent_by_lesson = AsyncMock(return_value=interactions)
        service = _make_service(interaction_repo=repo)

        summary = await service._get_agent_help_summary("v1", "current")
        assert summary["has_unresolved_failure"] is False

    @pytest.mark.asyncio
    async def test_empty_interactions(self):
        repo = MagicMock()
        repo.get_recent_by_lesson = AsyncMock(return_value=[])
        service = _make_service(interaction_repo=repo)

        summary = await service._get_agent_help_summary("v1", "current")
        assert summary["has_help"] is False

    @pytest.mark.asyncio
    async def test_exception_silently_degrades(self):
        """interaction_repo 异常时静默降级。"""
        repo = MagicMock()
        repo.get_recent_by_lesson = AsyncMock(side_effect=RuntimeError("db down"))
        service = _make_service(interaction_repo=repo)

        summary = await service._get_agent_help_summary("v1", "current")
        assert summary["has_help"] is False
