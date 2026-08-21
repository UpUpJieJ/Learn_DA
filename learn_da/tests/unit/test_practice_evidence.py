"""
Task 7: 证据消费测试

- 推荐服务读取练习失败信号触发回补建议
- Agent FC tool get_exercise_summary 只读摘要
- Dashboard practice-stats 端点返回正确指标
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.learning.recommendation import RecommendationService
from app.practice.schemas import ExerciseAttemptSummary


# =====================================================
# 推荐服务：练习失败触发回补
# =====================================================


class TestRecommendationPracticeSignal:
    """推荐服务能读取练习失败信号"""

    def _make_service(
        self, practice_summaries: list[ExerciseAttemptSummary] | None = None
    ) -> RecommendationService:
        """构造带 mock practice_service 的推荐服务"""
        mock_repo = MagicMock()
        # 返回两节课：基础课 + 进阶课
        lesson_basic = {
            "slug": "polars-basics",
            "title": "Polars 基础",
            "topic": "data-analysis",
            "category": "polars",
            "difficulty": "beginner",
            "order": 1,
            "track": "polars_basics",
            "prerequisites": [],
            "recommended_next": ["polars-groupby"],
            "skill_tags": ["polars"],
            "is_review_friendly": True,
            "is_branch_point": False,
        }
        lesson_advanced = {
            "slug": "polars-groupby",
            "title": "Polars 分组",
            "topic": "data-analysis",
            "category": "polars",
            "difficulty": "intermediate",
            "order": 2,
            "track": "polars_basics",
            "prerequisites": ["polars-basics"],
            "recommended_next": [],
            "skill_tags": ["polars", "groupby"],
            "is_review_friendly": False,
            "is_branch_point": False,
        }
        mock_repo.list_lessons.return_value = [lesson_basic, lesson_advanced]

        mock_analytics = AsyncMock()
        # 不触发常规回补条件
        mock_analytics.get_lesson_specific_stats.return_value = {
            "codeRuns": 1,
            "aiHelps": 0,
            "completed": False,
        }

        mock_learner_state = AsyncMock()
        mock_learner_state.get_completed_lessons.return_value = ["polars-basics"]
        mock_learner_state.is_in_cooldown.return_value = False
        mock_learner_state.set_cooldown.return_value = None

        mock_practice = AsyncMock()
        if practice_summaries is not None:
            mock_practice.get_attempt_summaries.return_value = practice_summaries
        else:
            mock_practice.get_attempt_summaries.return_value = []

        return RecommendationService(
            repository=mock_repo,
            analytics_service=mock_analytics,
            learner_state_service=mock_learner_state,
            practice_service=mock_practice,
        )

    @pytest.mark.asyncio
    async def test_practice_failures_trigger_review(self):
        """连续 3 次练习失败应触发回补建议"""
        # 构造 3 条失败摘要
        failures = [
            ExerciseAttemptSummary(
                id=i,
                attempt_id=i,
                exercise_id="ex-001",
                lesson_slug="polars-groupby",
                execution_status="completed",
                verification_status="failed",
                failure_reason="stdout_mismatch",
                created_time="2026-07-30 10:00:00",
                duration_ms=100,
            )
            for i in range(1, 4)
        ]
        service = self._make_service(practice_summaries=failures)

        result = await service.get_recommendation(
            visitor_id="visitor-1",
            current_lesson_slug="polars-groupby",
        )

        # 应触发回补建议
        assert result.primary is not None
        assert result.primary.type == "review_lesson"
        assert result.primary.reason_code == "prerequisite_weak"
        assert "polars-basics" == result.primary.target_slug

    @pytest.mark.asyncio
    async def test_no_practice_failures_no_review(self):
        """练习全部通过时不触发回补"""
        passed = [
            ExerciseAttemptSummary(
                id=1,
                attempt_id=1,
                exercise_id="ex-001",
                lesson_slug="polars-groupby",
                execution_status="completed",
                verification_status="passed",
                failure_reason=None,
                created_time="2026-07-30 10:00:00",
                duration_ms=100,
            )
        ]
        service = self._make_service(practice_summaries=passed)

        result = await service.get_recommendation(
            visitor_id="visitor-1",
            current_lesson_slug="polars-groupby",
        )

        # 不应触发回补（可能是顺学或 None）
        if result.primary:
            assert result.primary.reason_code != "prerequisite_weak"

    @pytest.mark.asyncio
    async def test_practice_service_none_graceful(self):
        """practice_service 为 None 时不报错"""
        service = self._make_service()
        service.practice_service = None

        result = await service.get_recommendation(
            visitor_id="visitor-1",
            current_lesson_slug="polars-groupby",
        )
        # 不崩溃即可
        assert result is not None

    @pytest.mark.asyncio
    async def test_practice_service_exception_graceful(self):
        """practice_service 抛异常时静默降级"""
        service = self._make_service()
        service.practice_service.get_attempt_summaries.side_effect = RuntimeError(
            "db error"
        )

        result = await service.get_recommendation(
            visitor_id="visitor-1",
            current_lesson_slug="polars-groupby",
        )
        # 不崩溃，正常返回
        assert result is not None


# =====================================================
# Agent FC Tool: get_exercise_summary
# =====================================================


class TestFCToolExerciseSummary:
    """Agent get_exercise_summary 工具只读摘要"""

    @pytest.mark.asyncio
    async def test_returns_summaries_without_code(self):
        """返回摘要不包含完整代码"""
        from app.agent.fc_tools import FCToolExecutor

        mock_retriever = AsyncMock()
        mock_practice = AsyncMock()
        mock_practice.get_attempt_summaries.return_value = [
            ExerciseAttemptSummary(
                id=1,
                attempt_id=1,
                exercise_id="ex-001",
                lesson_slug="polars-basics",
                execution_status="completed",
                verification_status="passed",
                failure_reason=None,
                created_time="2026-07-30 10:00:00",
                duration_ms=200,
            )
        ]

        executor = FCToolExecutor(
            knowledge_retriever=mock_retriever,
            visitor_id="visitor-1",
            practice_service=mock_practice,
        )

        result = await executor.execute(
            "get_exercise_summary", '{"lesson_slug": "polars-basics"}'
        )

        assert result.ok is True
        import json

        data = json.loads(result.output)
        assert "attempts" in data
        assert len(data["attempts"]) == 1
        # 摘要不含 code 字段
        assert "code" not in data["attempts"][0]

    @pytest.mark.asyncio
    async def test_no_practice_service_returns_error(self):
        """practice_service 为 None 时返回错误"""
        from app.agent.fc_tools import FCToolExecutor

        mock_retriever = AsyncMock()
        executor = FCToolExecutor(
            knowledge_retriever=mock_retriever,
            visitor_id="visitor-1",
            practice_service=None,
        )

        result = await executor.execute("get_exercise_summary", "{}")
        assert result.ok is False
        import json

        data = json.loads(result.output)
        assert data["error"] == "unavailable"

    @pytest.mark.asyncio
    async def test_visitor_isolation(self):
        """工具使用服务端注入的 visitor_id"""
        from app.agent.fc_tools import FCToolExecutor

        mock_retriever = AsyncMock()
        mock_practice = AsyncMock()
        mock_practice.get_attempt_summaries.return_value = []

        executor = FCToolExecutor(
            knowledge_retriever=mock_retriever,
            visitor_id="server-visitor-123",
            practice_service=mock_practice,
        )

        await executor.execute("get_exercise_summary", "{}")

        # 验证传入的是服务端 visitor_id
        mock_practice.get_attempt_summaries.assert_called_once_with(
            visitor_id="server-visitor-123", lesson_slug=None, limit=10
        )


# =====================================================
# Dashboard practice-stats 逻辑测试
# =====================================================


class TestPracticeStatsLogic:
    """Dashboard 练习指标逻辑（服务层）"""

    @pytest.mark.asyncio
    async def test_count_passed_exercises(self):
        """count_passed_exercises 正确去重"""
        from app.practice.repository import PracticeRepository
        from app.practice.models import ExerciseAttempt

        # 使用内存 SQLite
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from app.core.database.base import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with async_session() as db:
            repo = PracticeRepository(db)

            # 同一 exercise 两次 passed → 只算 1
            await repo.create_attempt(
                visitor_id="v1",
                request_id="r1",
                lesson_slug="l1",
                exercise_id="ex-001",
                execution_id=None,
                source="playground",
                language="python",
                code="print(1)",
                execution_status="completed",
                verification_status="passed",
            )
            await repo.create_attempt(
                visitor_id="v1",
                request_id="r2",
                lesson_slug="l1",
                exercise_id="ex-001",
                execution_id=None,
                source="playground",
                language="python",
                code="print(2)",
                execution_status="completed",
                verification_status="passed",
            )
            # 不同 exercise passed → 算 1
            await repo.create_attempt(
                visitor_id="v1",
                request_id="r3",
                lesson_slug="l2",
                exercise_id="ex-002",
                execution_id=None,
                source="playground",
                language="python",
                code="print(3)",
                execution_status="completed",
                verification_status="passed",
            )
            await db.commit()

            count = await repo.count_passed_exercises("v1")
            assert count == 2  # ex-001 + ex-002

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_error_categories_aggregation(self):
        """错误类别正确聚合"""
        from app.practice.repository import PracticeRepository
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from app.core.database.base import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with async_session() as db:
            repo = PracticeRepository(db)

            for i, reason in enumerate(
                ["stdout_mismatch", "stdout_mismatch", "execution_error"]
            ):
                await repo.create_attempt(
                    visitor_id="v1",
                    request_id=f"r{i}",
                    lesson_slug="l1",
                    exercise_id="ex-001",
                    execution_id=None,
                    source="playground",
                    language="python",
                    code=f"print({i})",
                    execution_status="completed",
                    verification_status="failed",
                    failure_reason=reason,
                )
            await db.commit()

            errors = await repo.count_recent_errors("v1", "ex-001", 10)
            assert errors["stdout_mismatch"] == 2
            assert errors["execution_error"] == 1

        await engine.dispose()
