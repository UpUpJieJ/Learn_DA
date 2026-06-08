"""
Phase 2: 学习行为事件采集 Service
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.repository import LearningRepository

from .repository import AnalyticsRepository
from .schemas import (
    CodeSnapshotItem,
    CodeSnapshotRequest,
    CodeSnapshotResponse,
    EventTrackRequest,
    EventTrackResponse,
)


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AnalyticsRepository(db)

    async def track_event(self, req: EventTrackRequest) -> EventTrackResponse:
        """记录学习行为事件，同时更新用户画像和每日统计"""
        await self.repo.create_record(
            visitor_id=req.visitor_id,
            event_type=req.event_type,
            lesson_slug=req.lesson_slug,
            duration_seconds=req.duration_seconds,
        )
        await self.repo.update_profile_stats(
            visitor_id=req.visitor_id,
            event_type=req.event_type,
            duration_seconds=req.duration_seconds,
        )
        await self.repo.upsert_daily_stats(
            event_type=req.event_type,
            visitor_id=req.visitor_id,
            duration_seconds=req.duration_seconds,
        )
        await self.repo.increment_active_users(req.visitor_id)
        await self.db.commit()
        return EventTrackResponse(recorded=True)

    async def save_snapshot(self, req: CodeSnapshotRequest) -> CodeSnapshotResponse:
        """保存代码快照"""
        snapshot = await self.repo.create_snapshot(
            visitor_id=req.visitor_id,
            code=req.code,
            lesson_slug=req.lesson_slug,
            language=req.language,
            description=req.description,
        )
        await self.db.commit()
        return CodeSnapshotResponse(snapshot_id=snapshot.id, version=snapshot.version)

    async def list_snapshots(
        self, visitor_id: str, lesson_slug: str | None = None
    ) -> list[CodeSnapshotItem]:
        """获取代码快照列表"""
        snapshots = await self.repo.list_snapshots(visitor_id, lesson_slug)
        return [
            CodeSnapshotItem(
                id=s.id,
                lesson_slug=s.lesson_slug,
                code=s.code,
                language=s.language,
                version=s.version,
                description=s.description,
                created_time=s.created_time.strftime("%Y-%m-%d %H:%M:%S") if s.created_time else "",
            )
            for s in snapshots
        ]

    # ── 首页统计 ─────────────────────────────────────────

    async def get_home_stats(self) -> dict:
        """获取首页展示的统计数据"""
        total_learners = await self.repo.get_total_learners()
        today_active = await self.repo.get_today_active_users()
        total_code_runs = await self.repo.get_total_code_runs()

        return {
            "totalLearners": total_learners,
            "todayActiveUsers": today_active,
            "totalCodeRuns": total_code_runs,
            "totalLessons": len(LearningRepository().list_lessons()),
        }

    # ── Dashboard ────────────────────────────────────────

    async def get_user_profile(self, visitor_id: str) -> dict:
        """获取用户画像"""
        profile = await self.repo.get_user_profile(visitor_id)
        if profile is None:
            return {
                "totalLearningMinutes": 0,
                "lessonsCompleted": 0,
                "codeRuns": 0,
                "aiHelps": 0,
                "currentStreak": 0,
                "longestStreak": 0,
                "lastActiveDate": None,
                "polarsScore": 0.0,
                "duckdbScore": 0.0,
                "sqlScore": 0.0,
                "dataProcessingScore": 0.0,
                "apiMasteryScore": 0.0,
            }
        return {
            "totalLearningMinutes": profile.total_learning_minutes,
            "lessonsCompleted": profile.lessons_completed,
            "codeRuns": profile.code_runs,
            "aiHelps": profile.ai_helps,
            "currentStreak": profile.current_streak,
            "longestStreak": profile.longest_streak,
            "lastActiveDate": profile.last_active_date,
            "polarsScore": profile.polars_score,
            "duckdbScore": profile.duckdb_score,
            "sqlScore": profile.sql_score,
            "dataProcessingScore": profile.data_processing_score,
            "apiMasteryScore": profile.api_mastery_score,
        }

    async def get_user_lesson_stats(self, visitor_id: str) -> dict:
        """获取用户课程统计"""
        return await self.repo.get_user_lesson_stats(visitor_id)

    async def get_daily_trend(self, days: int = 30) -> list[dict]:
        """获取每日趋势"""
        return await self.repo.get_daily_trend(days)

    async def get_category_progress(self, visitor_id: str) -> dict:
        """获取分类进度"""
        return await self.repo.get_category_progress(visitor_id)

    # ── 回补建议查询 ─────────────────────────────────────

    async def get_lesson_specific_stats(
        self, visitor_id: str, lesson_slug: str
    ) -> dict[str, int | bool]:
        """获取用户在特定课程的学习统计（用于回补建议）"""
        return await self.repo.get_lesson_specific_stats(visitor_id, lesson_slug)

    async def get_lesson_snapshots_count(self, visitor_id: str, lesson_slug: str) -> int:
        """获取用户在特定课程的代码快照数量（用于回补建议）"""
        return await self.repo.get_lesson_snapshots_count(visitor_id, lesson_slug)

    # ── 回流建议查询 ─────────────────────────────────────

    async def get_incomplete_lessons_with_activity(
        self, visitor_id: str, completed_lessons: list[str]
    ) -> list[dict]:
        """获取有活动但未完成的课程列表（用于回流建议）"""
        return await self.repo.get_incomplete_lessons_with_activity(
            visitor_id, completed_lessons
        )
