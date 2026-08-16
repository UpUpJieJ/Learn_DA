"""
Phase 2 & 3 & 4 & 5: 学习行为事件采集 + 学习流优化 + 首页统计 + Dashboard API
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db, get_anonymous_visitor_id
from app.learning.repository import LearningRepository
from app.utils.base_response import StdResp
from app.utils.limiter import limiter
from config.settings import settings

from .schemas import (
    EventTrackRequest,
    EventTrackResponse,
)
from .service import AnalyticsService

router = APIRouter(tags=["analytics"])


# ── Phase 2: 事件采集 ───────────────────────────────────


@router.post("/analytics/track", response_model=StdResp[EventTrackResponse])
@limiter.limit(settings.RATE_LIMIT_ANALYTICS_WRITE)
async def track_event(
    request: Request,
    req: EventTrackRequest,
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """记录学习行为事件"""
    service = AnalyticsService(db)
    result = await service.track_event(req, visitor_id)
    return StdResp.success(data=result)



# ── Phase 3: 学习流优化 ─────────────────────────────────


@router.get("/analytics/learning-progress")
async def get_learning_progress(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户学习进度（已完成课程列表 + 各课程统计）"""
    service = AnalyticsService(db)
    result = await service.get_user_lesson_stats(visitor_id)
    return StdResp.success(data=result)


@router.get("/analytics/recommended-lessons", deprecated=True)
async def get_recommended_lessons(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """
    [DEPRECATED] 基于用户进度推荐下一节课

    此接口已被 `/learning/recommendations` 替代。
    保留用于前端 Dashboard 的旧版 fallback 展示，将在后续版本移除。
    """
    service = AnalyticsService(db)
    repo = LearningRepository()

    # 获取用户已完成的课程
    lesson_stats = await service.get_user_lesson_stats(visitor_id)
    completed_slugs = set(lesson_stats.get("completedLessons", []))

    # 获取全部课程
    all_lessons = repo.list_lessons()
    all_lessons.sort(key=lambda x: x.order)

    # 推荐逻辑：找第一个未完成的课程
    recommended = None
    for lesson in all_lessons:
        if lesson.slug not in completed_slugs:
            recommended = {
                "slug": lesson.slug,
                "title": lesson.title,
                "description": lesson.description,
                "category": lesson.category,
                "difficulty": lesson.difficulty,
                "estimatedMinutes": lesson.estimated_minutes,
                "order": lesson.order,
                "tags": lesson.tags,
            }
            break

    # 如果全部完成，推荐第一个课程（重学）
    if recommended is None and all_lessons:
        first = all_lessons[0]
        recommended = {
            "slug": first.slug,
            "title": first.title,
            "description": first.description,
            "category": first.category,
            "difficulty": first.difficulty,
            "estimatedMinutes": first.estimated_minutes,
            "order": first.order,
            "tags": first.tags,
        }

    return StdResp.success(
        data={
            "recommended": recommended,
            "completedCount": len(completed_slugs),
            "totalCount": len(all_lessons),
        }
    )


# ── Phase 4: 首页统计 ───────────────────────────────────


@router.get("/analytics/home-stats")
async def get_home_stats(
    db: AsyncSession = Depends(get_db),
):
    """获取首页展示的统计数据（总学习人数、今日活跃、代码运行次数）"""
    service = AnalyticsService(db)
    result = await service.get_home_stats()
    return StdResp.success(data=result)


# ── Phase 5: Dashboard ──────────────────────────────────


@router.get("/analytics/user-profile")
async def get_user_profile(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户画像（累计学习时长、连续天数、能力雷达图分数）"""
    service = AnalyticsService(db)
    result = await service.get_user_profile(visitor_id)
    return StdResp.success(data=result)


@router.get("/analytics/user-lesson-stats")
async def get_user_lesson_stats(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户课程维度统计"""
    service = AnalyticsService(db)
    result = await service.get_user_lesson_stats(visitor_id)
    return StdResp.success(data=result)


@router.get("/analytics/daily-trend")
async def get_daily_trend(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """获取平台每日趋势数据"""
    service = AnalyticsService(db)
    result = await service.get_daily_trend(days)
    return StdResp.success(data=result)


@router.get("/analytics/category-progress")
async def get_category_progress(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户各分类学习进度"""
    service = AnalyticsService(db)
    result = await service.get_category_progress(visitor_id)
    return StdResp.success(data=result)


# ── Phase 2: 练习指标 ────────────────────────────────


@router.get("/analytics/practice-stats")
async def get_practice_stats(
    visitor_id: str = Depends(get_anonymous_visitor_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户练习指标：验证通过数、最近尝试、可恢复练习、错误类别

    阶段 3：新增 Agent 帮助后通过率与未解决失败聚合指标。
    """
    from app.agent.repository import AgentInteractionRepository
    from app.practice.repository import PracticeRepository
    from app.practice.service import PracticeService

    repo = PracticeRepository(db)
    service = PracticeService(db=db, practice_repo=repo)
    interaction_repo = AgentInteractionRepository(db)

    # 验证通过数
    passed_count = await repo.count_passed_exercises(visitor_id)
    total_attempts = await repo.count_attempts(visitor_id)

    # 最近尝试摘要
    recent_attempts = await service.get_attempt_summaries(visitor_id, limit=5)

    # 可恢复练习：最近未通过的练习（按 exercise_id 去重）
    all_recent = await repo.get_attempt_summaries_by_visitor(visitor_id, limit=50)
    resumable: list[dict] = []
    seen_exercises: set[str] = set()
    for a in all_recent:
        if (
            a.verification_status in ("failed", "not_run", "unverifiable")
            and a.exercise_id not in seen_exercises
        ):
            seen_exercises.add(a.exercise_id)
            resumable.append(
                {
                    "exerciseId": a.exercise_id,
                    "lessonSlug": a.lesson_slug,
                    "lastStatus": a.verification_status,
                }
            )
        if len(resumable) >= 5:
            break

    # 错误类别统计（最近 20 次尝试）
    recent_for_errors = await repo.get_attempt_summaries_by_visitor(
        visitor_id, limit=20
    )
    error_categories: dict[str, int] = {}
    for a in recent_for_errors:
        if a.failure_reason:
            error_categories[a.failure_reason] = (
                error_categories.get(a.failure_reason, 0) + 1
            )

    # 阶段 3：Agent 帮助后通过率 / 未解决失败聚合
    help_then_pass_rate = await _compute_help_then_pass_rate(
        interaction_repo, repo, visitor_id
    )
    unresolved_failures = len(resumable)

    return StdResp.success(
        data={
            "passedExercises": passed_count,
            "totalAttempts": total_attempts,
            "recentAttempts": [s.model_dump(by_alias=True) for s in recent_attempts],
            "resumableExercises": resumable,
            "errorCategories": error_categories,
            "helpThenPassRate": help_then_pass_rate,
            "unresolvedFailures": unresolved_failures,
        }
    )


async def _compute_help_then_pass_rate(
    interaction_repo, practice_repo, visitor_id: str
) -> float | None:
    """计算"获得 Agent 帮助（Level≥2）后最终通过"的比率。

    分子：有 evidence_state ∈ {execution_failed, verification_failed}
    且 hint_level ≥ 2 的 interaction，且对应 exercise 后续有通过 attempt。
    分母：上述 interaction 涉及的 exercise 总数。
    无数据时返回 None（前端降级显示）。
    """
    try:
        from sqlalchemy import select
        from app.agent.models import AgentInteraction

        stmt = (
            select(AgentInteraction)
            .where(
                AgentInteraction.visitor_id == visitor_id,
                AgentInteraction.evidence_state.in_(
                    ("execution_failed", "verification_failed")
                ),
                AgentInteraction.hint_level >= 2,
                AgentInteraction.is_deleted == False,  # noqa: E712
            )
            .order_by(AgentInteraction.created_time.desc())
            .limit(50)
        )
        result = await interaction_repo.db.execute(stmt)
        interactions = list(result.scalars().all())
    except Exception:
        return None

    if not interactions:
        return None

    # interaction 通过 attempt_id 关联具体练习；旧数据没有 attempt_id 时
    # 无法计算可靠的帮助后通过率，应排除而不是按课程粗略猜测。
    interaction_attempts: list[tuple[object, object]] = []
    for it in interactions:
        if it.attempt_id is None or it.created_time is None:
            continue
        try:
            attempt = await practice_repo.get_by_id(it.attempt_id, visitor_id)
        except Exception:
            continue
        if attempt is not None:
            interaction_attempts.append((it, attempt))

    if not interaction_attempts:
        return None

    passed = 0
    total = len(interaction_attempts)
    for interaction, attempt in interaction_attempts:
        try:
            passed_after = await practice_repo.get_passed_after(
                visitor_id,
                attempt.exercise_id,
                interaction.created_time,
            )
            if passed_after is not None:
                passed += 1
        except Exception:
            continue

    return round(passed / total, 4) if total else None
