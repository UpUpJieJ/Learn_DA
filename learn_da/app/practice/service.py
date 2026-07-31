"""
Phase 2: 可验证练习闭环 - PracticeService

练习执行编排、Attempt 管理、恢复 API 和完成边界。
"""

from __future__ import annotations

import logging
from typing import Any

from app.learning.repository import LearningRepository
from app.sandbox.schemas import ExecutionStatus

from .models import ExerciseAttempt
from .repository import PracticeRepository
from .schemas import (
    ExerciseAttemptDetail,
    ExerciseAttemptSummary,
    ExerciseResumeResponse,
    VerificationResult,
)
from .validator import verify

log = logging.getLogger(__name__)


class PracticeService:
    """练习服务：编排练习执行、判定和恢复"""

    def __init__(self, db: Any, practice_repo: PracticeRepository):
        self.db = db
        self.repo = practice_repo
        self._learning_repo = LearningRepository()

    def get_exercise_definition(
        self, lesson_slug: str, exercise_id: str
    ) -> dict[str, Any] | None:
        """获取练习定义"""
        lesson = self._learning_repo.get_lesson(lesson_slug)
        if lesson is None:
            return None
        if lesson.exercise is None:
            return None
        if lesson.exercise.id != exercise_id:
            return None
        return {
            "id": lesson.exercise.id,
            "title": lesson.exercise.title,
            "language": lesson.exercise.language,
            "starter_code": lesson.exercise.starter_code,
            "objective": lesson.exercise.objective,
            "hints": lesson.exercise.hints,
            "validator": lesson.exercise.validator.model_dump(by_alias=True),
        }

    async def create_or_replay_attempt(
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
    ) -> tuple[ExerciseAttempt, bool]:
        """创建或重放 Attempt。

        Returns:
            (attempt, created): created=False 表示重放命中
        """
        # 幂等检查
        existing = await self.repo.get_by_request_id(visitor_id, request_id)
        if existing:
            return existing, False

        attempt = await self.repo.create_attempt(
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
        return attempt, True

    async def verify_attempt(
        self,
        *,
        attempt: ExerciseAttempt,
        validator_type: str,
        expected: Any,
        stdout: str = "",
        stderr: str = "",
        dataframe: dict[str, Any] | None = None,
    ) -> VerificationResult:
        """对 Attempt 执行验证并更新状态"""
        result = verify(
            validator_type=validator_type,
            expected=expected,
            stdout=stdout,
            stderr=stderr,
            execution_status=attempt.execution_status,
            dataframe=dataframe,
        )

        attempt.verification_status = result.status
        attempt.failure_reason = result.failure_reason
        await self.db.flush()

        return VerificationResult(
            status=result.status,
            failure_reason=result.failure_reason,
            validator_type=result.validator_type,
        )

    async def get_resume_data(
        self, visitor_id: str, lesson_slug: str, exercise_id: str
    ) -> ExerciseResumeResponse | None:
        """获取恢复练习数据"""
        exercise_def = self.get_exercise_definition(lesson_slug, exercise_id)
        if exercise_def is None:
            return None

        # 找最近未通过的尝试
        latest_unpassed = await self.repo.get_latest_unpassed(visitor_id, exercise_id)

        if latest_unpassed:
            last_attempt = _to_summary(latest_unpassed)
            return ExerciseResumeResponse(
                exercise_id=exercise_id,
                lesson_slug=lesson_slug,
                code=latest_unpassed.code,
                language=latest_unpassed.language,
                is_resumed=True,
                last_attempt=last_attempt,
                exercise_title=exercise_def["title"],
                objective=exercise_def["objective"],
                hints=exercise_def["hints"],
                starter_code=exercise_def["starter_code"],
            )

        # fallback 到 starter code
        return ExerciseResumeResponse(
            exercise_id=exercise_id,
            lesson_slug=lesson_slug,
            code=exercise_def["starter_code"],
            language=exercise_def["language"],
            is_resumed=False,
            last_attempt=None,
            exercise_title=exercise_def["title"],
            objective=exercise_def["objective"],
            hints=exercise_def["hints"],
            starter_code=exercise_def["starter_code"],
        )

    async def get_attempt_detail(
        self, attempt_id: int, visitor_id: str
    ) -> ExerciseAttemptDetail | None:
        """获取单条尝试详情"""
        attempt = await self.repo.get_by_id(attempt_id, visitor_id)
        if attempt is None:
            return None
        return _to_detail(attempt)

    async def get_attempt_summaries(
        self,
        visitor_id: str,
        lesson_slug: str | None = None,
        limit: int = 20,
        exercise_id: str | None = None,
    ) -> list[ExerciseAttemptSummary]:
        """获取尝试摘要列表"""
        if exercise_id:
            attempts = await self.repo.get_recent_by_exercise(
                visitor_id, exercise_id, limit
            )
            if lesson_slug:
                attempts = [a for a in attempts if a.lesson_slug == lesson_slug]
        else:
            attempts = await self.repo.get_attempt_summaries_by_visitor(
                visitor_id, lesson_slug, limit
            )
        return [_to_summary(a) for a in attempts]

    async def get_exercise_stats(
        self, visitor_id: str, exercise_id: str
    ) -> dict[str, Any]:
        """获取某练习的统计信息"""
        recent = await self.repo.get_recent_by_exercise(visitor_id, exercise_id, 10)
        latest_passed = await self.repo.get_latest_passed(visitor_id, exercise_id)
        error_types = await self.repo.count_recent_errors(visitor_id, exercise_id, 10)

        return {
            "totalAttempts": len(recent),
            "hasPassed": latest_passed is not None,
            "lastPassedAt": (
                latest_passed.created_time.isoformat() if latest_passed else None
            ),
            "recentErrors": error_types,
        }


def _to_summary(a: ExerciseAttempt) -> ExerciseAttemptSummary:
    """ORM → 摘要 schema"""
    return ExerciseAttemptSummary(
        id=a.id,
        attempt_id=a.id,
        exercise_id=a.exercise_id,
        lesson_slug=a.lesson_slug,
        execution_status=a.execution_status,
        verification_status=a.verification_status,
        failure_reason=a.failure_reason,
        created_time=(
            a.created_time.strftime("%Y-%m-%d %H:%M:%S") if a.created_time else None
        ),
        duration_ms=a.duration_ms,
    )


def _to_detail(a: ExerciseAttempt) -> ExerciseAttemptDetail:
    """ORM → 详情 schema"""
    return ExerciseAttemptDetail(
        id=a.id,
        attempt_id=a.id,
        visitor_id=a.visitor_id,
        request_id=a.request_id,
        exercise_id=a.exercise_id,
        lesson_slug=a.lesson_slug,
        language=a.language,
        code=a.code,
        source=a.source,
        execution_status=a.execution_status,
        verification_status=a.verification_status,
        failure_reason=a.failure_reason,
        stdout=a.stdout,
        stderr=a.stderr,
        duration_ms=a.duration_ms,
        created_time=(
            a.created_time.strftime("%Y-%m-%d %H:%M:%S") if a.created_time else None
        ),
    )
