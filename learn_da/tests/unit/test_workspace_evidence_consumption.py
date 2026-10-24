"""
证据消费测试（改版 M4 起全部读工作区 ``task_attempts``）

- 推荐服务读取任务连续失败信号触发回补建议
- Agent FC tool get_task_summary 只读任务摘要
"""

import json
from datetime import datetime

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.learning.recommendation import RecommendationService


# =====================================================
# 推荐服务：任务连续失败触发回补
# =====================================================


class TestRecommendationTaskSignal:
    """推荐服务能读取工作区任务连续失败信号"""

    def _make_service(
        self, attempts: list | None = None, *, side_effect: Exception | None = None
    ) -> RecommendationService:
        """构造带 mock workspace_repo 的推荐服务"""
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

        mock_workspace = AsyncMock()
        if side_effect is not None:
            mock_workspace.recent_attempts.side_effect = side_effect
        else:
            mock_workspace.recent_attempts.return_value = attempts or []

        return RecommendationService(
            repository=mock_repo,
            analytics_service=mock_analytics,
            learner_state_service=mock_learner_state,
            workspace_repo=mock_workspace,
        )

    @staticmethod
    def _attempts(statuses: list[str]) -> list:
        from types import SimpleNamespace

        return [
            SimpleNamespace(
                id=index,
                task_id="t1",
                status=status,
                verdict="assertion_failed" if status != "passed" else "passed",
                lesson_slug="polars-groupby",
                attempt_no=index,
                created_time=datetime(2026, 7, 30, 10, 0, 0),
            )
            for index, status in enumerate(statuses, start=1)
        ]

    @pytest.mark.asyncio
    async def test_task_failures_trigger_review(self):
        """连续 3 次任务未通过应触发回补建议"""
        service = self._make_service(self._attempts(["failed", "failed", "failed"]))

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
    async def test_no_task_failures_no_review(self):
        """任务全部通过时不触发回补"""
        service = self._make_service(self._attempts(["passed"]))

        result = await service.get_recommendation(
            visitor_id="visitor-1",
            current_lesson_slug="polars-groupby",
        )

        # 不应触发回补（可能是顺学或 None）
        if result.primary:
            assert result.primary.reason_code != "prerequisite_weak"

    @pytest.mark.asyncio
    async def test_workspace_repo_none_graceful(self):
        """workspace_repo 为 None 时不报错"""
        service = self._make_service()
        service.workspace_repo = None

        result = await service.get_recommendation(
            visitor_id="visitor-1",
            current_lesson_slug="polars-groupby",
        )
        # 不崩溃即可
        assert result is not None

    @pytest.mark.asyncio
    async def test_workspace_repo_exception_graceful(self):
        """读任务记录抛异常时静默降级"""
        service = self._make_service(side_effect=RuntimeError("db error"))

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
