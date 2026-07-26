"""
阶段 1（重构）：学习行为事件采集 Service

事件记录与 Learner State 状态投影在同一事务中完成。
身份遵循阶段 0 签名匿名 session 约定，visitor_id 由 router 注入。
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.learner_state.service import LearnerStateService
from app.learning.repository import LearningRepository

from .repository import AnalyticsRepository
from .schemas import (
    CodeSnapshotItem,
    CodeSnapshotPage,
    CodeSnapshotRequest,
    CodeSnapshotResponse,
    EventTrackRequest,
    EventTrackResponse,
    EventType,
)


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AnalyticsRepository(db)
        self.learner_state = LearnerStateService(db)

    async def track_event(
        self, req: EventTrackRequest, visitor_id: str
    ) -> EventTrackResponse:
        """记录学习行为事件，同时更新用户画像、每日统计和 Learner State

        幂等保证：相同 ``event_id`` 重放时仅返回已存在记录，不再累加画像、每日
        统计或 Learner State 投影，确保“相同事件重放不改变最终投影”。

        并发兜底：``create_record`` 的先查后插在并发下仍可能双双查空，此时由
        ``learning_records.event_id`` 唯一索引拦下，整个事务回滚并按重放处理 ——
        重复上报不应该变成 500。
        """
        try:
            return await self._track_event(req, visitor_id)
        except IntegrityError:
            await self.db.rollback()
            return EventTrackResponse(recorded=True)

    async def _track_event(
        self, req: EventTrackRequest, visitor_id: str
    ) -> EventTrackResponse:
        # 幂等键：前端未提供时后端补一个 UUID，使每条事件都有稳定标识；
        # 但后端生成的 UUID 每次都不同，因此未带 event_id 的上报天然不参与去重。
        event_id = req.event_id or str(uuid.uuid4())
        event_type_str = (
            req.event_type.value
            if isinstance(req.event_type, EventType)
            else req.event_type
        )

        _, created = await self.repo.create_record(
            visitor_id=visitor_id,
            event_type=event_type_str,
            lesson_slug=req.lesson_slug,
            duration_seconds=req.duration_seconds,
            event_id=event_id,
            status=req.status,
        )

        # 重放命中：跳过所有副作用，保证投影幂等
        if not created:
            return EventTrackResponse(recorded=True)

        await self.repo.update_profile_stats(
            visitor_id=visitor_id,
            event_type=event_type_str,
            duration_seconds=req.duration_seconds,
        )
        await self.repo.upsert_daily_stats(
            event_type=event_type_str,
            visitor_id=visitor_id,
            duration_seconds=req.duration_seconds,
        )
        await self.repo.increment_active_users(visitor_id)

        # 联动 Learner State：事件记录和状态投影在同一事务中完成
        if req.lesson_slug:
            if req.event_type == EventType.LESSON_COMPLETE:
                await self.learner_state.complete_lesson(visitor_id, req.lesson_slug)
            elif req.event_type == EventType.LESSON_UNCOMPLETE:
                await self.learner_state.uncomplete_lesson(visitor_id, req.lesson_slug)
            elif req.event_type == EventType.LESSON_START:
                await self.learner_state.record_lesson_start(
                    visitor_id, req.lesson_slug
                )
            elif req.event_type == EventType.CODE_RUN:
                await self.learner_state.record_attempt(
                    visitor_id, req.lesson_slug, req.status or "success"
                )

        await self.db.commit()
        return EventTrackResponse(recorded=True)

    async def save_snapshot(
        self, req: CodeSnapshotRequest, visitor_id: str
    ) -> CodeSnapshotResponse:
        """保存代码快照，并在同一事务中记录 code_save 事件

        快照与 code_save 事件共享同一事务：任一失败则整体回滚，避免出现“有快照
        无事件”或“有事件无快照”的不一致。code_save 携带 event_id 以支持幂等。
        """
        snapshot = await self.repo.create_snapshot(
            visitor_id=visitor_id,
            code=req.code,
            lesson_slug=req.lesson_slug,
            language=req.language,
            description=req.description,
        )
        # Enforce retention: 100 per session, 10 000 global
        await self.repo.prune_snapshots(
            visitor_id, per_session_limit=100, global_limit=10_000
        )

        # 同事务记录 code_save 事件（不单独 commit，由本方法末尾统一提交）
        await self.repo.create_record(
            visitor_id=visitor_id,
            event_type=EventType.CODE_SAVE.value,
            lesson_slug=req.lesson_slug,
            event_id=f"code_save:{snapshot.id}",
        )

        await self.db.commit()
        return CodeSnapshotResponse(snapshot_id=snapshot.id, version=snapshot.version)

    async def list_snapshots(
        self,
        visitor_id: str,
        lesson_slug: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CodeSnapshotPage:
        """Return paginated snapshots (newest-first)."""
        snapshots, total = await self.repo.list_snapshots(
            visitor_id,
            lesson_slug,
            page=page,
            page_size=page_size,
        )
        items = [
            CodeSnapshotItem(
                id=s.id,
                lesson_slug=s.lesson_slug,
                code=s.code,
                language=s.language,
                version=s.version,
                description=s.description,
                created_time=(
                    s.created_time.strftime("%Y-%m-%d %H:%M:%S")
                    if s.created_time
                    else ""
                ),
            )
            for s in snapshots
        ]
        return CodeSnapshotPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

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

    async def get_lesson_snapshots_count(
        self, visitor_id: str, lesson_slug: str
    ) -> int:
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
