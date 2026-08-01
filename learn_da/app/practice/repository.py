"""
Phase 2: 可验证练习闭环 - 数据访问层
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ExerciseAttempt


class PracticeRepository:
    """练习尝试的持久化访问层"""

    MAX_CODE_LENGTH = 10_000
    MAX_STDOUT_LENGTH = 50_000
    MAX_STDERR_LENGTH = 10_000

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_attempt(
        self,
        *,
        visitor_id: str,
        request_id: str,
        lesson_slug: str,
        exercise_id: str,
        execution_id: str | None,
        source: str,
        language: str,
        code: str,
        execution_status: str,
        verification_status: str = "not_run",
        failure_reason: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        duration_ms: int | None = None,
    ) -> ExerciseAttempt:
        """创建练习尝试记录。

        (visitor_id, request_id) 唯一约束保证重放幂等。
        重复提交返回已存在记录，不新增行。
        """
        # 检查幂等
        existing = await self._get_by_request_id(visitor_id, request_id)
        if existing:
            return existing

        # 截断长内容
        code = code[: self.MAX_CODE_LENGTH]
        stdout = (stdout or "")[: self.MAX_STDOUT_LENGTH]
        stderr = (stderr or "")[: self.MAX_STDERR_LENGTH]

        attempt = ExerciseAttempt(
            visitor_id=visitor_id,
            request_id=request_id,
            lesson_slug=lesson_slug,
            exercise_id=exercise_id,
            execution_id=execution_id,
            source=source,
            language=language,
            code=code,
            execution_status=execution_status,
            verification_status=verification_status,
            failure_reason=failure_reason,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def get_by_id(
        self, attempt_id: int, visitor_id: str
    ) -> ExerciseAttempt | None:
        """按 ID 和 visitor_id 查询单条尝试"""
        stmt = select(ExerciseAttempt).where(
            ExerciseAttempt.id == attempt_id,
            ExerciseAttempt.visitor_id == visitor_id,
            ExerciseAttempt.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent_by_exercise(
        self,
        visitor_id: str,
        exercise_id: str,
        limit: int = 5,
    ) -> list[ExerciseAttempt]:
        """获取 visitor 对某练习的最近尝试"""
        stmt = (
            select(ExerciseAttempt)
            .where(
                ExerciseAttempt.visitor_id == visitor_id,
                ExerciseAttempt.exercise_id == exercise_id,
                ExerciseAttempt.is_deleted == False,  # noqa: E712
            )
            .order_by(ExerciseAttempt.created_time.desc(), ExerciseAttempt.id.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_unpassed(
        self,
        visitor_id: str,
        exercise_id: str,
    ) -> ExerciseAttempt | None:
        """获取最近一次未通过的尝试（用于恢复）"""
        stmt = (
            select(ExerciseAttempt)
            .where(
                ExerciseAttempt.visitor_id == visitor_id,
                ExerciseAttempt.exercise_id == exercise_id,
                ExerciseAttempt.verification_status.in_(
                    ("failed", "not_run", "unverifiable")
                ),
                ExerciseAttempt.is_deleted == False,  # noqa: E712
            )
            .order_by(ExerciseAttempt.created_time.desc(), ExerciseAttempt.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_passed(
        self,
        visitor_id: str,
        exercise_id: str,
    ) -> ExerciseAttempt | None:
        """获取最近一次验证通过的尝试"""
        stmt = (
            select(ExerciseAttempt)
            .where(
                ExerciseAttempt.visitor_id == visitor_id,
                ExerciseAttempt.exercise_id == exercise_id,
                ExerciseAttempt.verification_status == "passed",
                ExerciseAttempt.is_deleted == False,  # noqa: E712
            )
            .order_by(ExerciseAttempt.created_time.desc(), ExerciseAttempt.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_passed_after(
        self,
        visitor_id: str,
        exercise_id: str,
        occurred_after: datetime,
    ) -> ExerciseAttempt | None:
        """获取某次 Agent 交互之后通过的尝试。

        通过时间和练习 ID 都必须匹配，避免把交互前的历史通过记录误算为
        "帮助后通过"，也避免同课程的其他练习污染指标。
        """
        stmt = (
            select(ExerciseAttempt)
            .where(
                ExerciseAttempt.visitor_id == visitor_id,
                ExerciseAttempt.exercise_id == exercise_id,
                ExerciseAttempt.verification_status == "passed",
                ExerciseAttempt.created_time > occurred_after,
                ExerciseAttempt.is_deleted == False,  # noqa: E712
            )
            .order_by(ExerciseAttempt.created_time.asc(), ExerciseAttempt.id.asc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_lesson(
        self,
        visitor_id: str,
        lesson_slug: str,
    ) -> ExerciseAttempt | None:
        """获取 visitor 对某课程的最近一次尝试（阶段 3 Agent 证据解析用）。

        始终带 visitor_id 过滤，禁止跨 visitor 查询。
        """
        stmt = (
            select(ExerciseAttempt)
            .where(
                ExerciseAttempt.visitor_id == visitor_id,
                ExerciseAttempt.lesson_slug == lesson_slug,
                ExerciseAttempt.is_deleted == False,  # noqa: E712
            )
            .order_by(ExerciseAttempt.created_time.desc(), ExerciseAttempt.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_attempt_summaries_by_visitor(
        self,
        visitor_id: str,
        lesson_slug: str | None = None,
        limit: int = 20,
    ) -> list[ExerciseAttempt]:
        """获取 visitor 的尝试摘要列表"""
        conditions = [
            ExerciseAttempt.visitor_id == visitor_id,
            ExerciseAttempt.is_deleted == False,  # noqa: E712
        ]
        if lesson_slug:
            conditions.append(ExerciseAttempt.lesson_slug == lesson_slug)

        stmt = (
            select(ExerciseAttempt)
            .where(*conditions)
            .order_by(ExerciseAttempt.created_time.desc(), ExerciseAttempt.id.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_passed_exercises(self, visitor_id: str) -> int:
        """统计 visitor 已通过验证的练习数（去重按 exercise_id）"""
        from sqlalchemy import func

        stmt = select(func.count(func.distinct(ExerciseAttempt.exercise_id))).where(
            ExerciseAttempt.visitor_id == visitor_id,
            ExerciseAttempt.verification_status == "passed",
            ExerciseAttempt.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def count_attempts(self, visitor_id: str) -> int:
        """统计 visitor 的有效练习尝试总数。"""
        from sqlalchemy import func

        stmt = select(func.count(ExerciseAttempt.id)).where(
            ExerciseAttempt.visitor_id == visitor_id,
            ExerciseAttempt.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def count_recent_errors(
        self, visitor_id: str, exercise_id: str, limit: int = 10
    ) -> dict[str, int]:
        """统计最近 N 次尝试的错误类型分布"""
        stmt = (
            select(ExerciseAttempt)
            .where(
                ExerciseAttempt.visitor_id == visitor_id,
                ExerciseAttempt.exercise_id == exercise_id,
                ExerciseAttempt.is_deleted == False,  # noqa: E712
            )
            .order_by(ExerciseAttempt.created_time.desc(), ExerciseAttempt.id.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        attempts = list(result.scalars().all())

        error_types: dict[str, int] = {}
        for a in attempts:
            key = a.failure_reason or a.execution_status
            error_types[key] = error_types.get(key, 0) + 1
        return error_types

    async def _get_by_request_id(
        self, visitor_id: str, request_id: str
    ) -> ExerciseAttempt | None:
        """按幂等键查询"""
        stmt = select(ExerciseAttempt).where(
            ExerciseAttempt.visitor_id == visitor_id,
            ExerciseAttempt.request_id == request_id,
            ExerciseAttempt.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_request_id(
        self, visitor_id: str, request_id: str
    ) -> ExerciseAttempt | None:
        """按 visitor 和请求幂等键读取 Attempt。"""
        return await self._get_by_request_id(visitor_id, request_id)
