"""
Task 2: Attempt 数据模型、迁移与 repository 测试

验收标准：
- 重放不新增 Attempt
- 跨 visitor 不可读取
- 代码和输出长度受限
"""

import pytest

from app.practice.models import ExerciseAttempt
from app.practice.repository import PracticeRepository


# =====================================================
# 基础 CRUD
# =====================================================


class TestAttemptCreation:
    """ExerciseAttempt 创建与幂等"""

    async def test_create_attempt_basic(self, db_session):
        """基本创建"""
        repo = PracticeRepository(db_session)
        attempt = await repo.create_attempt(
            visitor_id="v1",
            request_id="req-001",
            lesson_slug="python-functions",
            exercise_id="python-functions-add-bonus-v1",
            execution_id="exec-001",
            source="playground",
            language="python",
            code="print('hello')",
            execution_status="success",
            verification_status="passed",
            stdout="hello",
        )
        assert attempt.id is not None
        assert attempt.visitor_id == "v1"
        assert attempt.request_id == "req-001"
        assert attempt.verification_status == "passed"

    async def test_replay_returns_same_attempt(self, db_session):
        """相同 (visitor_id, request_id) 重放返回已有记录，不新增"""
        repo = PracticeRepository(db_session)

        first = await repo.create_attempt(
            visitor_id="v1",
            request_id="req-dup",
            lesson_slug="polars-basics",
            exercise_id="polars-basics-filter-select-v1",
            execution_id="exec-002",
            source="playground",
            language="python",
            code="import polars as pl",
            execution_status="success",
        )

        second = await repo.create_attempt(
            visitor_id="v1",
            request_id="req-dup",
            lesson_slug="polars-basics",
            exercise_id="polars-basics-filter-select-v1",
            execution_id="exec-003",
            source="playground",
            language="python",
            code="different code",
            execution_status="error",
        )

        assert first.id == second.id
        assert second.code == "import polars as pl"  # 保留首次内容

    async def test_different_request_id_creates_new(self, db_session):
        """不同 request_id 创建新 Attempt"""
        repo = PracticeRepository(db_session)

        a1 = await repo.create_attempt(
            visitor_id="v1",
            request_id="req-a",
            lesson_slug="python-functions",
            exercise_id="ex-1",
            execution_id=None,
            source="playground",
            language="python",
            code="code a",
            execution_status="success",
        )
        a2 = await repo.create_attempt(
            visitor_id="v1",
            request_id="req-b",
            lesson_slug="python-functions",
            exercise_id="ex-1",
            execution_id=None,
            source="playground",
            language="python",
            code="code b",
            execution_status="success",
        )
        assert a1.id != a2.id


# =====================================================
# Visitor 隔离
# =====================================================


class TestVisitorIsolation:
    """跨 visitor 不可读取"""

    async def test_get_by_id_wrong_visitor_returns_none(self, db_session):
        """其他 visitor 无法按 ID 读取"""
        repo = PracticeRepository(db_session)
        attempt = await repo.create_attempt(
            visitor_id="owner",
            request_id="req-iso",
            lesson_slug="python-functions",
            exercise_id="ex-1",
            execution_id=None,
            source="playground",
            language="python",
            code="secret",
            execution_status="success",
        )

        result = await repo.get_by_id(attempt.id, visitor_id="intruder")
        assert result is None

    async def test_get_recent_by_exercise_isolated(self, db_session):
        """recent 查询只返回本 visitor 的记录"""
        repo = PracticeRepository(db_session)

        await repo.create_attempt(
            visitor_id="alice",
            request_id="req-alice",
            lesson_slug="python-functions",
            exercise_id="ex-shared",
            execution_id=None,
            source="playground",
            language="python",
            code="alice code",
            execution_status="success",
        )
        await repo.create_attempt(
            visitor_id="bob",
            request_id="req-bob",
            lesson_slug="python-functions",
            exercise_id="ex-shared",
            execution_id=None,
            source="playground",
            language="python",
            code="bob code",
            execution_status="success",
        )

        alice_attempts = await repo.get_recent_by_exercise("alice", "ex-shared")
        bob_attempts = await repo.get_recent_by_exercise("bob", "ex-shared")

        assert len(alice_attempts) == 1
        assert alice_attempts[0].code == "alice code"
        assert len(bob_attempts) == 1
        assert bob_attempts[0].code == "bob code"


# =====================================================
# 长度截断
# =====================================================


class TestTruncation:
    """代码和输出长度受限"""

    async def test_code_truncated(self, db_session):
        """超长代码被截断到 MAX_CODE_LENGTH"""
        repo = PracticeRepository(db_session)
        long_code = "x" * 20_000

        attempt = await repo.create_attempt(
            visitor_id="v1",
            request_id="req-long",
            lesson_slug="python-functions",
            exercise_id="ex-1",
            execution_id=None,
            source="playground",
            language="python",
            code=long_code,
            execution_status="success",
        )
        assert len(attempt.code) == PracticeRepository.MAX_CODE_LENGTH

    async def test_stdout_truncated(self, db_session):
        """超长 stdout 被截断"""
        repo = PracticeRepository(db_session)
        long_stdout = "o" * 100_000

        attempt = await repo.create_attempt(
            visitor_id="v1",
            request_id="req-stdout",
            lesson_slug="python-functions",
            exercise_id="ex-1",
            execution_id=None,
            source="playground",
            language="python",
            code="print('x')",
            execution_status="success",
            stdout=long_stdout,
        )
        assert len(attempt.stdout) == PracticeRepository.MAX_STDOUT_LENGTH


# =====================================================
# 查询方法
# =====================================================


class TestQueries:
    """按 visitor + exercise 查询"""

    async def test_get_latest_unpassed(self, db_session):
        """获取最近未通过尝试"""
        repo = PracticeRepository(db_session)

        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-1",
            lesson_slug="l",
            exercise_id="ex",
            execution_id=None,
            source="playground",
            language="python",
            code="old",
            execution_status="success",
            verification_status="failed",
        )
        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-2",
            lesson_slug="l",
            exercise_id="ex",
            execution_id=None,
            source="playground",
            language="python",
            code="new",
            execution_status="success",
            verification_status="failed",
        )

        latest = await repo.get_latest_unpassed("v1", "ex")
        assert latest is not None
        assert latest.code == "new"

    async def test_get_latest_passed(self, db_session):
        """获取最近通过尝试"""
        repo = PracticeRepository(db_session)

        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-p1",
            lesson_slug="l",
            exercise_id="ex",
            execution_id=None,
            source="playground",
            language="python",
            code="passed code",
            execution_status="success",
            verification_status="passed",
        )

        latest = await repo.get_latest_passed("v1", "ex")
        assert latest is not None
        assert latest.verification_status == "passed"

    async def test_count_passed_exercises(self, db_session):
        """统计已通过练习数（去重）"""
        repo = PracticeRepository(db_session)

        # 同一 exercise 两次通过
        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-c1",
            lesson_slug="l",
            exercise_id="ex-a",
            execution_id=None,
            source="playground",
            language="python",
            code="c1",
            execution_status="success",
            verification_status="passed",
        )
        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-c2",
            lesson_slug="l",
            exercise_id="ex-a",
            execution_id=None,
            source="playground",
            language="python",
            code="c2",
            execution_status="success",
            verification_status="passed",
        )
        # 另一个 exercise
        await repo.create_attempt(
            visitor_id="v1",
            request_id="req-c3",
            lesson_slug="l",
            exercise_id="ex-b",
            execution_id=None,
            source="playground",
            language="python",
            code="c3",
            execution_status="success",
            verification_status="passed",
        )

        count = await repo.count_passed_exercises("v1")
        assert count == 2  # ex-a 和 ex-b

    async def test_count_attempts_is_visitor_scoped(self, db_session):
        repo = PracticeRepository(db_session)
        for request_id, visitor_id in (
            ("req-v1-a", "v1"),
            ("req-v1-b", "v1"),
            ("req-v2-a", "v2"),
        ):
            await repo.create_attempt(
                visitor_id=visitor_id,
                request_id=request_id,
                lesson_slug="python-functions",
                exercise_id="python-functions-add-bonus-v1",
                execution_id=None,
                source="playground",
                language="python",
                code="print(100)",
                execution_status="success",
            )

        assert await repo.count_attempts("v1") == 2
        assert await repo.count_attempts("v2") == 1
