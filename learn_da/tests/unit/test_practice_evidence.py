"""
Task 7: 证据消费测试

- 推荐服务读取练习失败信号触发回补建议
- Agent FC tool get_task_summary 只读任务摘要（改版 M4 起读 task_attempts）
- Dashboard practice-stats 端点返回正确指标
"""

import json
from datetime import datetime

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
# Agent FC Tool: get_task_summary（改版 M4：读 task_attempts）
# =====================================================


class TestFCToolTaskSummary:
    """Agent get_task_summary 工具只读任务摘要"""

    @staticmethod
    def _attempt(**overrides):
        from types import SimpleNamespace

        base = {
            "task_id": "t1",
            "attempt_no": 2,
            "status": "failed",
            "verdict": "assertion_failed",
            "created_time": datetime(2026, 10, 22, 10, 0, 0),
            "assertions": json.dumps(
                [
                    {"id": "t1-schema", "title": "列齐全", "status": "passed"},
                    {
                        "id": "t1-rows",
                        "title": "分组行数",
                        "status": "failed",
                        "detail": "表达式为假",
                        "actual": "表达式 'region_stats.height == 4' 为假（实际值：False）",
                    },
                ],
                ensure_ascii=False,
            ),
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    @pytest.mark.asyncio
    async def test_returns_failed_assertions_without_code(self):
        """返回失败断言与实际值，且不含完整代码"""
        from app.agent.fc_tools import FCToolExecutor

        mock_repo = AsyncMock()
        mock_repo.recent_attempts.return_value = [self._attempt()]

        executor = FCToolExecutor(
            knowledge_retriever=AsyncMock(),
            visitor_id="visitor-1",
            workspace_repo=mock_repo,
            current_lesson="polars-groupby",
        )

        result = await executor.execute("get_task_summary", "{}")

        assert result.ok is True
        data = json.loads(result.output)
        assert data["lesson_slug"] == "polars-groupby"
        assert data["total"] == 1
        item = data["attempts"][0]
        assert item["verdict"] == "assertion_failed"
        # 只回失败断言（通过的被过滤），并带实际值
        assert [a["id"] for a in item["failed_assertions"]] == ["t1-rows"]
        assert "实际值：False" in item["failed_assertions"][0]["actual"]
        assert "code" not in item

    @pytest.mark.asyncio
    async def test_filters_by_task_id(self):
        """传 task_id 时只返回该任务的提交"""
        from app.agent.fc_tools import FCToolExecutor

        mock_repo = AsyncMock()
        mock_repo.recent_attempts.return_value = [
            self._attempt(task_id="t1"),
            self._attempt(task_id="t2", attempt_no=1),
        ]
        executor = FCToolExecutor(
            knowledge_retriever=AsyncMock(),
            visitor_id="visitor-1",
            workspace_repo=mock_repo,
        )

        result = await executor.execute("get_task_summary", '{"task_id": "t2"}')

        data = json.loads(result.output)
        assert data["total"] == 1
        assert data["attempts"][0]["task_id"] == "t2"

    @pytest.mark.asyncio
    async def test_no_workspace_repo_returns_error(self):
        """workspace_repo 为 None 时返回 unavailable"""
        from app.agent.fc_tools import FCToolExecutor

        executor = FCToolExecutor(
            knowledge_retriever=AsyncMock(),
            visitor_id="visitor-1",
            workspace_repo=None,
        )

        result = await executor.execute("get_task_summary", "{}")
        assert result.ok is False
        data = json.loads(result.output)
        assert data["error"] == "unavailable"

    @pytest.mark.asyncio
    async def test_visitor_isolation(self):
        """工具使用服务端注入的 visitor_id，模型无法指定"""
        from app.agent.fc_tools import FCToolExecutor

        mock_repo = AsyncMock()
        mock_repo.recent_attempts.return_value = []

        executor = FCToolExecutor(
            knowledge_retriever=AsyncMock(),
            visitor_id="server-visitor-123",
            workspace_repo=mock_repo,
            current_lesson="polars-basics",
        )

        await executor.execute("get_task_summary", '{"visitor_id": "attacker"}')

        mock_repo.recent_attempts.assert_awaited_once_with(
            "server-visitor-123", lesson_slug="polars-basics", limit=10
        )

    @pytest.mark.asyncio
    async def test_learner_progress_includes_task_stats(self):
        """学习进度工具同时给出工作区任务进度"""
        from app.agent.fc_tools import FCToolExecutor

        mock_repo = AsyncMock()
        mock_repo.progress.return_value = {
            "summary": {"tasksPassed": 2, "tasksTotal": 3},
            "lessons": [
                {
                    "lessonSlug": "polars-basics",
                    "title": "Polars 基础",
                    "status": "in_progress",
                    "passedTasks": 2,
                    "totalTasks": 3,
                    "currentTaskId": "t3",
                    "attempts": 4,
                },
                {
                    "lessonSlug": "duckdb-analytics",
                    "title": "DuckDB 入门",
                    "status": "not_started",
                    "passedTasks": 0,
                    "totalTasks": 3,
                    "currentTaskId": "t1",
                    "attempts": 0,
                },
            ],
        }

        executor = FCToolExecutor(
            knowledge_retriever=AsyncMock(),
            visitor_id="visitor-1",
            workspace_repo=mock_repo,
        )

        result = await executor.execute("get_learner_progress", "{}")

        data = json.loads(result.output)
        assert data["summary"]["tasksPassed"] == 2
        # 没进度的课程被过滤，避免把 13 门课全塞给模型
        assert [item["lesson_slug"] for item in data["lessons"]] == ["polars-basics"]
        assert data["lessons"][0]["current_task"] == "t3"


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
