"""
Task 5: 恢复 API 与完成边界测试

验收标准：
- 刷新可恢复最近未通过代码
- 验证通过后仍未完成（不自动写 lesson_complete）
- 确认动作后才完成（通过 analytics/track）
"""

import pytest

from app.practice.repository import PracticeRepository
from app.practice.service import PracticeService


# =====================================================
# 恢复 API
# =====================================================


class TestResumeAPI:
    """GET /playground/exercises/{exercise_id}/resume"""

    async def test_resume_returns_latest_unpassed_code(self, db_session):
        """有未通过尝试 → 返回最近代码"""
        repo = PracticeRepository(db_session)
        service = PracticeService(db=db_session, practice_repo=repo)

        # 创建两次失败尝试
        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-old",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
            execution_id=None,
            source="playground",
            language="python",
            code="old code",
            execution_status="success",
            verification_status="failed",
        )
        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-new",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
            execution_id=None,
            source="playground",
            language="python",
            code="new code",
            execution_status="success",
            verification_status="failed",
        )

        result = await service.get_resume_data(
            "v1", "python-functions", "python-functions-add-bonus-v1"
        )

        assert result is not None
        assert result.is_resumed is True
        assert result.code == "new code"
        assert result.last_attempt is not None

    async def test_resume_fallback_to_starter_code(self, db_session):
        """无尝试 → 返回 starter code"""
        repo = PracticeRepository(db_session)
        service = PracticeService(db=db_session, practice_repo=repo)

        result = await service.get_resume_data(
            "v1", "python-functions", "python-functions-add-bonus-v1"
        )

        assert result is not None
        assert result.is_resumed is False
        assert "add_bonus" in result.code  # starter code 包含函数名
        assert result.last_attempt is None

    async def test_resume_after_passed_still_returns_starter(self, db_session):
        """已通过 → 无未通过尝试 → 返回 starter code"""
        repo = PracticeRepository(db_session)
        service = PracticeService(db=db_session, practice_repo=repo)

        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-passed",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
            execution_id=None,
            source="playground",
            language="python",
            code="correct code",
            execution_status="success",
            verification_status="passed",
        )

        result = await service.get_resume_data(
            "v1", "python-functions", "python-functions-add-bonus-v1"
        )

        assert result is not None
        assert result.is_resumed is False  # 没有未通过的，返回 starter

    async def test_resume_nonexistent_exercise_returns_none(self, db_session):
        """练习不存在 → None"""
        repo = PracticeRepository(db_session)
        service = PracticeService(db=db_session, practice_repo=repo)

        result = await service.get_resume_data(
            "v1", "nonexistent", "nonexistent-exercise"
        )
        assert result is None

    async def test_resume_visitor_isolation(self, db_session):
        """恢复只返回本 visitor 的代码"""
        repo = PracticeRepository(db_session)
        service = PracticeService(db=db_session, practice_repo=repo)

        await repo.create_attempt(
            visitor_id="alice",
            request_id="req-alice",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
            execution_id=None,
            source="playground",
            language="python",
            code="alice secret code",
            execution_status="success",
            verification_status="failed",
        )

        # bob 恢复时不应看到 alice 的代码
        result = await service.get_resume_data(
            "bob", "python-functions", "python-functions-add-bonus-v1"
        )
        assert result is not None
        assert result.is_resumed is False
        assert "alice" not in result.code


# =====================================================
# 完成边界
# =====================================================


class TestCompletionBoundary:
    """验证通过后不自动完成课程"""

    async def test_verification_passed_does_not_complete_lesson(self, db_session):
        """验证通过 → LearnerLessonProgress 不应自动变为 completed"""
        from app.learner_state.service import LearnerStateService

        repo = PracticeRepository(db_session)
        service = PracticeService(db=db_session, practice_repo=repo)
        learner_state = LearnerStateService(db_session)

        # 创建通过的 Attempt
        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-pass",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
            execution_id=None,
            source="playground",
            language="python",
            code="correct",
            execution_status="success",
            verification_status="passed",
        )
        await db_session.flush()

        # 检查 Learner State：不应自动完成
        completed = await learner_state.get_completed_lessons("v1")
        assert "python-functions" not in completed

    async def test_explicit_complete_via_learner_state(self, db_session):
        """显式调用 complete_lesson 后才完成"""
        from app.learner_state.service import LearnerStateService

        learner_state = LearnerStateService(db_session)

        # 模拟用户确认完成（通过 analytics/track 触发）
        await learner_state.complete_lesson("v1", "python-functions")
        await db_session.flush()

        completed = await learner_state.get_completed_lessons("v1")
        assert "python-functions" in completed

    async def test_attempt_summary_does_not_expose_code(self, db_session):
        """摘要不暴露完整代码（Agent/推荐只读摘要）"""
        repo = PracticeRepository(db_session)
        service = PracticeService(db=db_session, practice_repo=repo)

        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-sum",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
            execution_id=None,
            source="playground",
            language="python",
            code="secret implementation code",
            execution_status="success",
            verification_status="passed",
        )

        summaries = await service.get_attempt_summaries("v1", "python-functions")
        assert len(summaries) == 1

        summary = summaries[0]
        # 摘要不应包含 code 字段
        assert not hasattr(summary, "code") or summary.model_dump().get("code") is None
        assert summary.verification_status == "passed"


# =====================================================
# API 集成测试（通过 HTTP client）
# 注：路由注册在测试环境可能不完整，核心逻辑已在服务层验证
# =====================================================


class TestResumeEndpoint:
    """通过 HTTP 测试 resume endpoint"""

    async def test_resume_endpoint_returns_200(self, client):
        """GET /playground/exercises/{id}/resume 正常返回"""
        resp = await client.get(
            "/api/v1/playground/exercises/python-functions-add-bonus-v1/resume",
            params={"lessonSlug": "python-functions"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["exerciseId"] == "python-functions-add-bonus-v1"
        assert data["data"]["isResumed"] is False  # 无历史尝试

    async def test_resume_endpoint_nonexistent_404(self, client):
        """练习不存在 → 404"""
        resp = await client.get(
            "/api/v1/playground/exercises/nonexistent/resume",
            params={"lessonSlug": "nonexistent"},
        )
        assert resp.status_code == 200  # StdResp 包装，code=404
        data = resp.json()
        assert data["code"] == 404
