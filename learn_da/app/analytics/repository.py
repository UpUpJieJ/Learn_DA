"""
Phase 2: 学习行为数据访问层
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CodeSnapshot, DailyStats, LearningRecord, UserProfile


class AnalyticsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 事件记录 ─────────────────────────────────────────

    async def create_record(
        self,
        visitor_id: str,
        event_type: str,
        lesson_slug: str | None = None,
        duration_seconds: int | None = None,
    ) -> LearningRecord:
        record = LearningRecord(
            visitor_id=visitor_id,
            event_type=event_type,
            lesson_slug=lesson_slug,
            duration_seconds=duration_seconds,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    # ── 用户画像 ─────────────────────────────────────────

    async def get_or_create_profile(self, visitor_id: str) -> UserProfile:
        stmt = select(UserProfile).where(
            UserProfile.visitor_id == visitor_id,
            UserProfile.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = UserProfile(visitor_id=visitor_id)
            self.db.add(profile)
            await self.db.flush()
        return profile

    async def update_profile_stats(
        self,
        visitor_id: str,
        event_type: str,
        duration_seconds: int | None = None,
    ) -> UserProfile:
        profile = await self.get_or_create_profile(visitor_id)

        if event_type == "code_run":
            profile.code_runs += 1
        elif event_type == "ai_help":
            profile.ai_helps += 1
        elif event_type == "lesson_complete":
            profile.lessons_completed += 1

        if duration_seconds and duration_seconds > 0:
            profile.total_learning_minutes += duration_seconds // 60

        # 连续学习天数计算
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if profile.last_active_date != today_str:
            try:
                last = datetime.strptime(profile.last_active_date or "", "%Y-%m-%d").date()
                from datetime import date
                today = date.today()
                if (today - last).days == 1:
                    profile.current_streak += 1
                elif (today - last).days > 1:
                    profile.current_streak = 1
                # 同一天不更新
            except (ValueError, TypeError):
                profile.current_streak = 1

            if profile.current_streak > profile.longest_streak:
                profile.longest_streak = profile.current_streak
            profile.last_active_date = today_str

        await self.db.flush()
        return profile

    # ── 每日统计 ─────────────────────────────────────────

    async def upsert_daily_stats(
        self,
        event_type: str,
        visitor_id: str,
        duration_seconds: int | None = None,
    ) -> None:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stmt = select(DailyStats).where(
            DailyStats.stat_date == today_str,
            DailyStats.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        stats = result.scalar_one_or_none()

        if stats is None:
            stats = DailyStats(stat_date=today_str)
            self.db.add(stats)
            await self.db.flush()

        if event_type == "code_run":
            stats.code_runs += 1
        elif event_type == "lesson_complete":
            stats.lessons_completed += 1
        elif event_type == "ai_help":
            stats.ai_helps += 1

        if duration_seconds and duration_seconds > 0:
            # 简单移动平均
            total = stats.active_users or 1
            stats.avg_session_minutes = (
                (stats.avg_session_minutes * (total - 1) + duration_seconds / 60) / total
            )

        await self.db.flush()

    async def increment_active_users(self, visitor_id: str) -> None:
        """检查今日是否已计入活跃用户，若未计入则 +1"""
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stmt = select(DailyStats).where(
            DailyStats.stat_date == today_str,
            DailyStats.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        stats = result.scalar_one_or_none()

        if stats is None:
            stats = DailyStats(stat_date=today_str, active_users=1)
            self.db.add(stats)
            await self.db.flush()
            return

        # 检查该 visitor 今日是否已有记录
        exists_stmt = select(func.count()).select_from(LearningRecord).where(
            LearningRecord.visitor_id == visitor_id,
            func.date(LearningRecord.created_time) == today_str,
            LearningRecord.is_deleted == False,  # noqa: E712
        )
        exists_result = await self.db.execute(exists_stmt)
        count = exists_result.scalar() or 0
        if count <= 1:  # 刚插入的那条也算
            stats.active_users += 1
            await self.db.flush()

    # ── 代码快照 ─────────────────────────────────────────

    async def create_snapshot(
        self,
        visitor_id: str,
        code: str,
        lesson_slug: str | None = None,
        language: str = "python",
        description: str | None = None,
    ) -> CodeSnapshot:
        # 获取当前最大版本号
        stmt = (
            select(func.max(CodeSnapshot.version))
            .where(
                CodeSnapshot.visitor_id == visitor_id,
                CodeSnapshot.lesson_slug == lesson_slug,
                CodeSnapshot.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        max_version = result.scalar() or 0

        snapshot = CodeSnapshot(
            visitor_id=visitor_id,
            lesson_slug=lesson_slug,
            code=code,
            language=language,
            version=max_version + 1,
            description=description,
        )
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

    async def list_snapshots(
        self,
        visitor_id: str,
        lesson_slug: str | None = None,
    ) -> list[CodeSnapshot]:
        stmt = (
            select(CodeSnapshot)
            .where(
                CodeSnapshot.visitor_id == visitor_id,
                CodeSnapshot.is_deleted == False,  # noqa: E712
            )
            .order_by(CodeSnapshot.created_time.desc())
        )
        if lesson_slug:
            stmt = stmt.where(CodeSnapshot.lesson_slug == lesson_slug)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ── 首页统计查询 ─────────────────────────────────────

    async def get_total_learners(self) -> int:
        stmt = select(func.count()).select_from(UserProfile).where(
            UserProfile.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_today_active_users(self) -> int:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stmt = select(DailyStats.active_users).where(
            DailyStats.stat_date == today_str,
            DailyStats.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_total_code_runs(self) -> int:
        stmt = select(func.sum(DailyStats.code_runs)).where(
            DailyStats.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ── Dashboard 查询 ───────────────────────────────────

    async def get_user_profile(self, visitor_id: str) -> UserProfile | None:
        stmt = select(UserProfile).where(
            UserProfile.visitor_id == visitor_id,
            UserProfile.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_lesson_stats(self, visitor_id: str) -> dict:
        """获取用户各课程的学习统计"""
        stmt = (
            select(
                LearningRecord.lesson_slug,
                LearningRecord.event_type,
                func.count().label("count"),
            )
            .where(
                LearningRecord.visitor_id == visitor_id,
                LearningRecord.lesson_slug.isnot(None),
                LearningRecord.is_deleted == False,  # noqa: E712
            )
            .group_by(LearningRecord.lesson_slug, LearningRecord.event_type)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        lesson_stats: dict = {}
        for row in rows:
            slug = row.lesson_slug
            if slug not in lesson_stats:
                lesson_stats[slug] = {"slug": slug, "codeRuns": 0, "aiHelps": 0, "completed": False}
            if row.event_type == "code_run":
                lesson_stats[slug]["codeRuns"] = row.count
            elif row.event_type == "ai_help":
                lesson_stats[slug]["aiHelps"] = row.count
            elif row.event_type == "lesson_complete":
                lesson_stats[slug]["completed"] = True

        return {
            "completedLessons": [s["slug"] for s in lesson_stats.values() if s["completed"]],
            "lessonDetails": list(lesson_stats.values()),
        }

    async def get_daily_trend(self, days: int = 30) -> list[dict]:
        stmt = (
            select(DailyStats)
            .where(DailyStats.is_deleted == False)  # noqa: E712
            .order_by(DailyStats.stat_date.desc())
            .limit(days)
        )
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return [
            {
                "date": r.stat_date,
                "activeUsers": r.active_users,
                "codeRuns": r.code_runs,
                "lessonsCompleted": r.lessons_completed,
                "aiHelps": r.ai_helps,
            }
            for r in rows
        ]

    async def get_category_progress(self, visitor_id: str) -> dict:
        """获取用户各分类的学习进度"""
        from app.analytics.models import LearningRecord
        stmt = (
            select(
                LearningRecord.lesson_slug,
                func.count().filter(LearningRecord.event_type == "lesson_complete").label("completed"),
            )
            .where(
                LearningRecord.visitor_id == visitor_id,
                LearningRecord.is_deleted == False,  # noqa: E712
            )
            .group_by(LearningRecord.lesson_slug)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        # 简单按 slug 前缀分类
        category_completed = {"polars": 0, "duckdb": 0, "combined": 0}
        for row in rows:
            if row.lesson_slug:
                for cat in category_completed:
                    if cat in row.lesson_slug:
                        category_completed[cat] += row.completed or 0

        return category_completed
