import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.core.session import get_anonymous_visitor_id
from app.practice.models import ExerciseAttempt
from app.practice.repository import PracticeRepository
from app.practice.service import PracticeService
from app.sandbox import RunnerUnavailableError, SandboxService
from app.sandbox.schemas import ExecutionStatus
from app.utils.base_response import StdResp
from app.utils.limiter import limiter
from config.settings import settings

from .schemas import (
    ExecuteCodeRequest,
    ExecuteCodeResponse,
    FormatCodeRequest,
    FormatCodeResponse,
)
from .service import PlaygroundService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/playground", tags=["playground"])


def get_playground_service(request: Request) -> PlaygroundService:
    runner_client = request.app.state.runner_client
    return PlaygroundService(
        sandbox_service=SandboxService(runner_client=runner_client)
    )


@router.post("/execute")
@limiter.limit(settings.RATE_LIMIT_PLAYGROUND_EXECUTE)
async def execute_code(
    request: Request,
    payload: ExecuteCodeRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """执行代码（普通执行或练习执行）"""
    # 练习参数成对校验：必须同时提供或同时不提供
    has_lesson = bool(payload.lesson_slug)
    has_exercise = bool(payload.exercise_id)
    if has_lesson != has_exercise:
        return StdResp.error(
            msg="lessonSlug 和 exerciseId 必须同时提供",
            code=422,
        ).to_response()

    # 练习执行：需要 DB session 在同一事务中写 Attempt + code_run + Learner State
    if has_lesson and has_exercise:
        return await _execute_exercise(request, payload, visitor_id, db)

    # 普通执行（无 DB 写入）
    try:
        service = get_playground_service(request)
        result = await service.execute(payload)
        return StdResp.success(data=result.model_dump(by_alias=True))
    except RunnerUnavailableError:
        return _runner_unavailable_response(payload)


async def _execute_exercise(
    request: Request,
    payload: ExecuteCodeRequest,
    visitor_id: str,
    db: AsyncSession,
):
    """练习执行：Runner 失败也必须保存 Attempt（审计要求）"""
    practice_repo = PracticeRepository(db)
    practice_service = PracticeService(db=db, practice_repo=practice_repo)

    # 前置校验：练习定义必须存在
    exercise_def = practice_service.get_exercise_definition(
        payload.lesson_slug, payload.exercise_id
    )
    if exercise_def is None:
        return StdResp.error(
            msg=f"练习 '{payload.exercise_id}' 不存在于课程 '{payload.lesson_slug}'",
            code=422,
        ).to_response()
    if exercise_def["language"] != payload.language:
        return StdResp.error(
            msg=(
                f"练习 '{payload.exercise_id}' 要求 {exercise_def['language']}，"
                f"收到 {payload.language}"
            ),
            code=422,
        ).to_response()

    # 幂等检查：如果 request_id 已存在，直接返回已有结果
    existing = await practice_repo.get_by_request_id(
        visitor_id, str(payload.request_id)
    )
    if existing:
        response = _attempt_response(payload, existing, exercise_def)
        return _exercise_http_response(response)

    # 调用 Runner 执行代码
    try:
        service = PlaygroundService(
            sandbox_service=SandboxService(
                runner_client=request.app.state.runner_client
            ),
            practice_service=practice_service,
        )
        result = await service.execute(payload, visitor_id=visitor_id)
    except RunnerUnavailableError:
        # Runner 不可用也必须保存 Attempt（审计要求）
        attempt, _ = await practice_service.create_or_replay_attempt(
            visitor_id=visitor_id,
            request_id=str(payload.request_id),
            lesson_slug=payload.lesson_slug,
            exercise_id=payload.exercise_id,
            execution_id=None,
            source=payload.source,
            language=payload.language,
            code=payload.code,
            execution_status="unavailable",
            verification_status="unverifiable",
            failure_reason="runner_unavailable",
        )
        await _record_attempt_projection(
            db=db,
            visitor_id=visitor_id,
            lesson_slug=payload.lesson_slug,
            request_id=str(payload.request_id),
            status="unavailable",
        )
        await db.commit()
        response = _attempt_response(payload, attempt, exercise_def)
        return _exercise_http_response(response)
    except Exception:
        await db.rollback()
        raise

    # 同事务：写 code_run 事件 + 更新 Learner State
    await _record_attempt_projection(
        db=db,
        visitor_id=visitor_id,
        lesson_slug=payload.lesson_slug,
        request_id=str(payload.request_id),
        status=result.status,
    )

    await db.commit()
    return StdResp.success(data=result.model_dump(by_alias=True))


async def _record_attempt_projection(
    *,
    db: AsyncSession,
    visitor_id: str,
    lesson_slug: str,
    request_id: str,
    status: str,
) -> None:
    """写入幂等事件，并且只在首次写入时更新学习投影。"""
    from app.analytics.repository import AnalyticsRepository
    from app.learner_state.service import LearnerStateService

    analytics_repo = AnalyticsRepository(db)
    _record, created = await analytics_repo.create_record(
        visitor_id=visitor_id,
        event_type="code_run",
        lesson_slug=lesson_slug,
        event_id=request_id,
        status=status,
    )
    if not created:
        return

    await analytics_repo.update_profile_stats(
        visitor_id=visitor_id, event_type="code_run"
    )
    await LearnerStateService(db).record_attempt(
        visitor_id=visitor_id,
        lesson_slug=lesson_slug,
        status=status,
    )


def _attempt_response(
    payload: ExecuteCodeRequest,
    attempt: ExerciseAttempt,
    exercise_def: dict,
) -> ExecuteCodeResponse:
    from .schemas import ExerciseVerification

    return ExecuteCodeResponse(
        request_id=payload.request_id,
        execution_id=attempt.execution_id,
        source=payload.source,
        status=attempt.execution_status,
        stdout=attempt.stdout or "",
        stderr=attempt.stderr or "",
        error_type=(
            "runner_unavailable"
            if attempt.execution_status == ExecutionStatus.UNAVAILABLE
            else None
        ),
        duration_ms=attempt.duration_ms or 0,
        result_type=(
            "error"
            if attempt.execution_status
            in {
                ExecutionStatus.ERROR,
                ExecutionStatus.TIMEOUT,
                ExecutionStatus.REJECTED,
                ExecutionStatus.UNAVAILABLE,
            }
            else "text"
        ),
        attempt_id=attempt.id,
        verification=ExerciseVerification(
            status=attempt.verification_status,
            failure_reason=attempt.failure_reason,
            validator_type=exercise_def["validator"]["type"],
        ),
    )


def _exercise_http_response(result: ExecuteCodeResponse):
    if result.status == ExecutionStatus.UNAVAILABLE:
        return StdResp.error(
            msg="Execution service unavailable",
            code=503,
            data=result.model_dump(mode="json", by_alias=True),
        ).to_response()
    return StdResp.success(data=result.model_dump(by_alias=True))


def _runner_unavailable_response(payload: ExecuteCodeRequest):
    log.warning("Runner unavailable during playground execution")
    unavailable = ExecuteCodeResponse(
        request_id=payload.request_id,
        status=ExecutionStatus.UNAVAILABLE,
        stdout="",
        stderr="",
        error_type="runner_unavailable",
        duration_ms=0,
    )
    return StdResp.error(
        msg="Execution service unavailable",
        code=503,
        data=unavailable.model_dump(mode="json", by_alias=True),
    ).to_response()


@router.post("/format", response_model=StdResp[FormatCodeResponse])
async def format_code(
    payload: FormatCodeRequest,
    request: Request,
):
    service = get_playground_service(request)
    return StdResp.success(data=service.format_code(payload))
