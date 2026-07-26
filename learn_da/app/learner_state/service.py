"""
阶段 1：统一学习事实 - LearnerStateService

学习者状态的唯一权威来源。管理课程完成状态、进度投影和推荐冷却。
所有需要读取"学习者当前处于什么状态"的模块（Dashboard、Learning、推荐、Agent）
都应通过本服务获取数据，而不是直接查询事件表或信任客户端参数。
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import LearnerLessonProgress, RecommendationCooldown
from .schemas import LearnerProgressSummary, LessonProgressDetail


class LearnerStateService:
    """学习者状态深模块：外部接口小，内部隐藏状态计算和持久化细节。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 状态写入 ─────────────────────────────────────────

    async def record_lesson_start(self, visitor_id: str, lesson_slug: str) -> None:
        """记录课程开始/访问（upsert：不存在则创建，存在则更新 last_activity_at）"""
        progress = await self._get_or_create(visitor_id, lesson_slug)
        now = datetime.now(timezone.utc)
        progress.last_activity_at = now
        await self.db.flush()

    async def complete_lesson(self, visitor_id: str, lesson_slug: str) -> None:
        """标记课程完成（upsert 语义，幂等）"""
        progress = await self._get_or_create(visitor_id, lesson_slug)
        now = datetime.now(timezone.utc)
        if progress.status != "completed":
            progress.status = "completed"
            progress.completed_at = now
        progress.last_activity_at = now
        await self.db.flush()

    async def uncomplete_lesson(self, visitor_id: str, lesson_slug: str) -> None:
        """撤销课程完成（将状态改为 uncompleted，保留历史记录）"""
        progress = await self._get_or_create(visitor_id, lesson_slug)
        now = datetime.now(timezone.utc)
        progress.status = "uncompleted"
        progress.completed_at = None
        progress.last_activity_at = now
        await self.db.flush()

    async def record_attempt(
        self, visitor_id: str, lesson_slug: str, status: str
    ) -> None:
        """记录代码尝试。

        ``status`` 由前端原样透传执行结果（success/error/timeout/rejected/
        unavailable）。这里只按 success 与否二分计数，明细留在
        ``learning_records.status`` 里供后续按错误类型聚合。
        """
        progress = await self._get_or_create(visitor_id, lesson_slug)
        now = datetime.now(timezone.utc)
        progress.attempt_count = (progress.attempt_count or 0) + 1
        if status == "success":
            progress.success_count = (progress.success_count or 0) + 1
        else:
            progress.error_count = (progress.error_count or 0) + 1
        progress.last_activity_at = now
        await self.db.flush()

    # ── 状态查询 ─────────────────────────────────────────

    async def get_completed_lessons(self, visitor_id: str) -> list[str]:
        """获取已完成课程 slug 列表（供推荐、Agent 复用）"""
        stmt = (
            select(LearnerLessonProgress.lesson_slug)
            .where(
                LearnerLessonProgress.visitor_id == visitor_id,
                LearnerLessonProgress.status == "completed",
                LearnerLessonProgress.is_deleted == False,  # noqa: E712
            )
            .order_by(LearnerLessonProgress.completed_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_lesson_progress(
        self, visitor_id: str, lesson_slug: str
    ) -> LessonProgressDetail | None:
        """获取单课进度详情"""
        progress = await self._get_progress_row(visitor_id, lesson_slug)
        if progress is None:
            return None
        return self._to_detail(progress)

    async def get_full_progress(self, visitor_id: str) -> LearnerProgressSummary:
        """获取完整进度投影（供前端统一状态接口使用）"""
        stmt = (
            select(LearnerLessonProgress).where(
                LearnerLessonProgress.visitor_id == visitor_id,
                LearnerLessonProgress.is_deleted == False,  # noqa: E712
            )
            # 显式 NULLS LAST：SQLite 与 PostgreSQL 对 DESC 下 NULL 的默认位置相反，
            # 否则 last_activity_at 为空的行会在 PG 上被当成“最近访问”。
            .order_by(nulls_last(LearnerLessonProgress.last_activity_at.desc()))
        )
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())

        completed_lessons = [r.lesson_slug for r in rows if r.status == "completed"]
        last_visited_slug = rows[0].lesson_slug if rows else None
        lesson_details = [self._to_detail(r) for r in rows]

        return LearnerProgressSummary(
            completed_lessons=completed_lessons,
            last_visited_slug=last_visited_slug,
            lesson_details=lesson_details,
            total_completed=len(completed_lessons),
            total_started=len(rows),
        )

    async def get_last_visited(self, visitor_id: str) -> str | None:
        """获取最近访问的课程 slug"""
        stmt = (
            select(LearnerLessonProgress.lesson_slug)
            .where(
                LearnerLessonProgress.visitor_id == visitor_id,
                LearnerLessonProgress.is_deleted == False,  # noqa: E712
            )
            .order_by(nulls_last(LearnerLessonProgress.last_activity_at.desc()))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ── 推荐冷却 ─────────────────────────────────────────

    async def is_in_cooldown(self, visitor_id: str, lesson_slug: str) -> bool:
        """检查某课程推荐是否在冷却期内"""
        now = datetime.now(timezone.utc)
        stmt = select(RecommendationCooldown).where(
            RecommendationCooldown.visitor_id == visitor_id,
            RecommendationCooldown.lesson_slug == lesson_slug,
            RecommendationCooldown.cooldown_until > now,
            RecommendationCooldown.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def set_cooldown(
        self, visitor_id: str, lesson_slug: str, seconds: int
    ) -> None:
        """设置推荐冷却（upsert 语义）"""
        now = datetime.now(timezone.utc)
        cooldown_until = now + timedelta(seconds=seconds)

        stmt = select(RecommendationCooldown).where(
            RecommendationCooldown.visitor_id == visitor_id,
            RecommendationCooldown.lesson_slug == lesson_slug,
            RecommendationCooldown.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.cooldown_until = cooldown_until
        else:
            cooldown = RecommendationCooldown(
                visitor_id=visitor_id,
                lesson_slug=lesson_slug,
                cooldown_until=cooldown_until,
            )
            self.db.add(cooldown)
        await self.db.flush()

    # ── 内部方法 ─────────────────────────────────────────

    async def _get_or_create(
        self, visitor_id: str, lesson_slug: str
    ) -> LearnerLessonProgress:
        """获取或创建进度行"""
        progress = await self._get_progress_row(visitor_id, lesson_slug)
        if progress is None:
            now = datetime.now(timezone.utc)
            progress = LearnerLessonProgress(
                visitor_id=visitor_id,
                lesson_slug=lesson_slug,
                status="started",
                last_activity_at=now,
                attempt_count=0,
                success_count=0,
                error_count=0,
            )
            self.db.add(progress)
            await self.db.flush()
        return progress

    async def _get_progress_row(
        self, visitor_id: str, lesson_slug: str
    ) -> LearnerLessonProgress | None:
        """查询单行进度记录"""
        stmt = select(LearnerLessonProgress).where(
            LearnerLessonProgress.visitor_id == visitor_id,
            LearnerLessonProgress.lesson_slug == lesson_slug,
            LearnerLessonProgress.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _to_detail(row: LearnerLessonProgress) -> LessonProgressDetail:
        """将 ORM 行转换为响应 schema"""
        return LessonProgressDetail(
            lesson_slug=row.lesson_slug,
            status=row.status,
            completed_at=(
                row.completed_at.strftime("%Y-%m-%d %H:%M:%S")
                if row.completed_at
                else None
            ),
            last_activity_at=(
                row.last_activity_at.strftime("%Y-%m-%d %H:%M:%S")
                if row.last_activity_at
                else None
            ),
            attempt_count=row.attempt_count or 0,
            success_count=row.success_count or 0,
            error_count=row.error_count or 0,
        )
