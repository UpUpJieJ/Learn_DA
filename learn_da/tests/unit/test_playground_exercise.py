"""
Task 4: Playground 练习执行编排测试

验收标准：
- 四类状态可区分（执行成功+验证通过、执行成功+验证失败、执行错误、Runner不可用）
- 重放无重复投影
- 普通执行回归不变
"""

from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy import select

from app.playground.schemas import ExecuteCodeRequest, ExecuteCodeResponse
from app.playground.service import PlaygroundService
from app.practice.models import ExerciseAttempt
from app.practice.repository import PracticeRepository
from app.practice.service import PracticeService
from app.sandbox import RunnerUnavailableError
from app.sandbox.schemas import SandboxExecutionResult, ExecutionStatus


# =====================================================
# Helpers
# =====================================================


def _mock_sandbox_result(
    status: str = "success",
    stdout: str = "100\n",
    stderr: str = "",
    duration_ms: int = 50,
) -> SandboxExecutionResult:
    return SandboxExecutionResult(
        execution_id=uuid4(),
        status=status,
        stdout=stdout,
        stderr=stderr,
        error_type=None if status == "success" else "RuntimeError",
        duration_ms=duration_ms,
        output_truncated=False,
    )


def _make_service(db_session, sandbox_result: SandboxExecutionResult):
    """构建带 mock sandbox 的 PlaygroundService"""
    mock_sandbox = AsyncMock()
    mock_sandbox.execute = AsyncMock(return_value=sandbox_result)

    practice_repo = PracticeRepository(db_session)
    practice_service = PracticeService(db=db_session, practice_repo=practice_repo)

    service = PlaygroundService(
        sandbox_service=mock_sandbox,
        practice_service=practice_service,
    )
    return service


# =====================================================
# 四类状态
# =====================================================


class TestExerciseOrchestration:
    """练习执行编排"""

    async def test_execution_success_verification_passed(self, db_session):
        """执行成功 + 验证通过"""
        sandbox_result = _mock_sandbox_result(status="success", stdout="100\n")
        service = _make_service(db_session, sandbox_result)

        payload = ExecuteCodeRequest(
            code="def add_bonus(score):\n    return score + 5\nprint(add_bonus(95))",
            language="python",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
        )

        response = await service.execute(payload, visitor_id="v1")

        assert response.status == "success"
        assert response.attempt_id is not None
        assert response.verification is not None
        assert response.verification.status == "passed"

    async def test_execution_success_verification_failed(self, db_session):
        """执行成功 + 验证失败（输出不匹配）"""
        sandbox_result = _mock_sandbox_result(status="success", stdout="99\n")
        service = _make_service(db_session, sandbox_result)

        payload = ExecuteCodeRequest(
            code="print(99)",
            language="python",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
        )

        response = await service.execute(payload, visitor_id="v1")

        assert response.status == "success"
        assert response.attempt_id is not None
        assert response.verification is not None
        assert response.verification.status == "failed"
        assert response.verification.failure_reason == "stdout_exact_mismatch"

    async def test_execution_error_is_unverifiable(self, db_session):
        """执行错误 → unverifiable（不是练习失败）"""
        sandbox_result = _mock_sandbox_result(
            status="error", stdout="", stderr="NameError: name 'x' is not defined"
        )
        service = _make_service(db_session, sandbox_result)

        payload = ExecuteCodeRequest(
            code="print(x)",
            language="python",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
        )

        response = await service.execute(payload, visitor_id="v1")

        assert response.status == "error"
        assert response.attempt_id is not None
        assert response.verification is not None
        assert response.verification.status == "unverifiable"
        assert "execution_error" in response.verification.failure_reason

    async def test_execution_timeout_is_unverifiable(self, db_session):
        """执行超时 → unverifiable"""
        sandbox_result = _mock_sandbox_result(status="timeout", stdout="")
        service = _make_service(db_session, sandbox_result)

        payload = ExecuteCodeRequest(
            code="while True: pass",
            language="python",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
        )

        response = await service.execute(payload, visitor_id="v1")

        assert response.status == "timeout"
        assert response.verification.status == "unverifiable"


# =====================================================
# 重放幂等
# =====================================================


class TestReplayIdempotency:
    """相同 request_id 重放不新增 Attempt"""

    async def test_replay_returns_same_attempt(self, db_session):
        """重放返回同一 attempt_id"""
        sandbox_result = _mock_sandbox_result(status="success", stdout="100\n")
        service = _make_service(db_session, sandbox_result)

        request_id = uuid4()
        payload = ExecuteCodeRequest(
            request_id=request_id,
            code="print(100)",
            language="python",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
        )

        r1 = await service.execute(payload, visitor_id="v1")
        r2 = await service.execute(payload, visitor_id="v1")

        assert r1.attempt_id == r2.attempt_id
        assert r1.verification.status == "passed"
        assert r2.verification.status == "passed"

    async def test_replay_does_not_duplicate_learner_state(self, db_session):
        """重放不重复写 Learner State（由 router 层保证，这里验证 Attempt 不重复）"""
        sandbox_result = _mock_sandbox_result(status="success", stdout="100\n")
        service = _make_service(db_session, sandbox_result)

        request_id = uuid4()
        payload = ExecuteCodeRequest(
            request_id=request_id,
            code="print(100)",
            language="python",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
        )

        await service.execute(payload, visitor_id="v1")
        await service.execute(payload, visitor_id="v1")

        # 检查只有一条 Attempt
        repo = PracticeRepository(db_session)
        attempts = await repo.get_recent_by_exercise(
            "v1", "python-functions-add-bonus-v1"
        )
        assert len(attempts) == 1


# =====================================================
# 普通执行回归
# =====================================================


class TestNormalExecutionRegression:
    """普通执行（无练习参数）行为不变"""

    async def test_no_exercise_params_no_attempt(self, db_session):
        """无 lesson_slug/exercise_id → 不创建 Attempt"""
        sandbox_result = _mock_sandbox_result(status="success", stdout="hello\n")
        service = _make_service(db_session, sandbox_result)

        payload = ExecuteCodeRequest(
            code="print('hello')",
            language="python",
        )

        response = await service.execute(payload, visitor_id="v1")

        assert response.status == "success"
        assert response.attempt_id is None
        assert response.verification is None

    async def test_no_visitor_id_no_attempt(self, db_session):
        """无 visitor_id → 不创建 Attempt（普通执行）"""
        sandbox_result = _mock_sandbox_result(status="success", stdout="hello\n")
        service = _make_service(db_session, sandbox_result)

        payload = ExecuteCodeRequest(
            code="print('hello')",
            language="python",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
        )

        response = await service.execute(payload)  # no visitor_id

        assert response.status == "success"
        assert response.attempt_id is None

    async def test_unknown_exercise_no_attempt(self, db_session):
        """练习不存在 → 不创建 Attempt，正常返回执行结果"""
        sandbox_result = _mock_sandbox_result(status="success", stdout="hello\n")
        service = _make_service(db_session, sandbox_result)

        payload = ExecuteCodeRequest(
            code="print('hello')",
            language="python",
            lesson_slug="nonexistent-lesson",
            exercise_id="nonexistent-exercise",
        )

        response = await service.execute(payload, visitor_id="v1")

        assert response.status == "success"
        assert response.attempt_id is None


class TestExerciseHTTPContract:
    async def test_partial_exercise_context_is_rejected(self, client):
        response = await client.post(
            "/api/v1/playground/execute",
            json={
                "code": "print(100)",
                "language": "python",
                "lessonSlug": "python-functions",
            },
        )

        assert response.status_code == 422
        assert response.json()["msg"] == "lessonSlug 和 exerciseId 必须同时提供"

    async def test_unknown_exercise_is_rejected_before_runner(self, client):
        from main import app

        response = await client.post(
            "/api/v1/playground/execute",
            json={
                "code": "print(100)",
                "language": "python",
                "lessonSlug": "python-functions",
                "exerciseId": "not-a-real-exercise",
            },
        )

        assert response.status_code == 422
        app.state.runner_client.execute.assert_not_awaited()

    async def test_language_mismatch_is_rejected_before_runner(self, client):
        from main import app

        response = await client.post(
            "/api/v1/playground/execute",
            json={
                "code": "select 1",
                "language": "sql",
                "lessonSlug": "python-functions",
                "exerciseId": "python-functions-add-bonus-v1",
            },
        )

        assert response.status_code == 422
        app.state.runner_client.execute.assert_not_awaited()

    async def test_runner_unavailable_persists_attempt_and_replays(self, test_engine):
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.core.database.database import get_db
        from app.learner_state.service import LearnerStateService
        from app.sandbox.client import RunnerClient
        from main import app

        session_factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        mock_runner = AsyncMock(spec=RunnerClient)
        mock_runner.execute.side_effect = RunnerUnavailableError("runner unavailable")
        app.state.runner_client = mock_runner
        request_id = str(uuid4())
        payload = {
            "requestId": request_id,
            "code": "print(100)",
            "language": "python",
            "lessonSlug": "python-functions",
            "exerciseId": "python-functions-add-bonus-v1",
        }

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as http_client:
                first = await http_client.post(
                    "/api/v1/playground/execute", json=payload
                )
                second = await http_client.post(
                    "/api/v1/playground/execute", json=payload
                )
        finally:
            app.dependency_overrides.clear()

        assert first.status_code == 503
        assert second.status_code == 503
        first_data = first.json()["data"]
        assert first_data["attemptId"] is not None
        assert first_data["executionId"] is None
        assert first_data["status"] == "unavailable"
        assert first_data["verification"]["status"] == "unverifiable"
        assert second.json()["data"]["attemptId"] == first_data["attemptId"]
        mock_runner.execute.assert_awaited_once()

        async with session_factory() as db_session:
            attempts = await db_session.execute(select(ExerciseAttempt))
            rows = list(attempts.scalars().all())
            matching = [a for a in rows if a.request_id == request_id]
            assert len(matching) == 1

            detail = await LearnerStateService(db_session).get_lesson_progress(
                matching[0].visitor_id, "python-functions"
            )
            assert detail is not None
            assert detail.attempt_count == 1
