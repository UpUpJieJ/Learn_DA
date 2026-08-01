"""
阶段 1：统一学习事实 - 推荐输入收口测试（适配阶段 0 签名 session）

覆盖场景：
- 推荐接口不依赖客户端 completedLessons
- 服务器侧从 LearnerState 读取完成状态
- 幂等事件写入（相同 event_id 不重复）
- 幂等重放不重复累加画像/每日统计/attempt 投影
- 事件联动 LearnerState（lesson_complete -> 状态投影更新）
- code_save 与快照同事务写入
- ai_help 由 Agent chat 后端成功受理时记录

注：track_event / save_snapshot 内部会 commit，因此需要 commit 的测试使用
独立 async_session（不包裹 session.begin()），与阶段 0 端点测试一致。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.learner_state.service import LearnerStateService
from app.analytics.repository import AnalyticsRepository
from app.analytics.service import AnalyticsService
from app.analytics.schemas import CodeSnapshotRequest, EventTrackRequest
from app.analytics.models import LearningRecord


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _standalone_session(test_engine):
    """创建不包裹 begin() 的独立会话，支持 service 内部 commit。"""
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    session = factory()
    try:
        yield session
    finally:
        await session.close()


@pytest.mark.anyio
async def test_recommendation_reads_from_learner_state(db_session):
    """推荐服务应从 LearnerState 获取完成状态，而非客户端参数"""
    from app.learning.recommendation import RecommendationService
    from app.learning.repository import LearningRepository

    learner_svc = LearnerStateService(db_session)
    # 通过 LearnerState 标记完成
    await learner_svc.complete_lesson("visitor-1", "polars-basics")
    await db_session.flush()

    rec_svc = RecommendationService(
        repository=LearningRepository(),
        learner_state_service=learner_svc,
    )
    # 即使传入空的 completed_lessons，服务内部应从 LearnerState 读取
    result = await rec_svc.get_recommendation(
        visitor_id="visitor-1",
        completed_lessons=[],  # 客户端传入空列表
        current_lesson_slug="polars-expressions",
    )

    # 推荐不应再推荐已完成的课程
    if result.primary:
        assert result.primary.target_slug != "polars-basics"


@pytest.mark.anyio
async def test_idempotent_event_write(db_session):
    """相同 event_id 的事件不应重复写入（不触发 commit 的 repo 层测试）"""
    repo = AnalyticsRepository(db_session)

    # 第一次写入
    record1, created1 = await repo.create_record(
        visitor_id="visitor-1",
        event_type="code_run",
        lesson_slug="polars-basics",
        event_id="unique-event-123",
        status="success",
    )
    assert record1 is not None
    assert created1 is True

    # 第二次写入相同 event_id
    record2, created2 = await repo.create_record(
        visitor_id="visitor-1",
        event_type="code_run",
        lesson_slug="polars-basics",
        event_id="unique-event-123",
        status="success",
    )

    # 应返回已有记录，不重复创建
    assert created2 is False
    assert record2.id == record1.id


@pytest.mark.anyio
async def test_idempotent_replay_does_not_double_count(test_engine):
    """相同 event_id 重放时，画像/每日统计/LearnerState 投影不应被重复累加"""
    async for session in _standalone_session(test_engine):
        analytics_svc = AnalyticsService(session)

        req = EventTrackRequest.model_validate(
            {
                "eventType": "code_run",
                "lessonSlug": "polars-basics",
                "eventId": "evt-replay-001",
                "status": "success",
            }
        )
        await analytics_svc.track_event(req, visitor_id="visitor-replay")
        # 重放同一事件
        await analytics_svc.track_event(req, visitor_id="visitor-replay")

        learner_svc = LearnerStateService(session)
        detail = await learner_svc.get_lesson_progress(
            "visitor-replay", "polars-basics"
        )
        assert detail is not None
        # 只应记录一次尝试
        assert detail.attempt_count == 1
        assert detail.success_count == 1
        assert detail.error_count == 0

        # 画像 code_runs 也只应 +1
        profile = await analytics_svc.repo.get_user_profile("visitor-replay")
        assert profile is not None
        assert profile.code_runs == 1


@pytest.mark.anyio
async def test_event_linkage_to_learner_state(test_engine):
    """lesson_complete 事件应联动更新 LearnerState"""
    async for session in _standalone_session(test_engine):
        analytics_svc = AnalyticsService(session)

        req = EventTrackRequest.model_validate(
            {
                "eventType": "lesson_complete",
                "lessonSlug": "polars-basics",
                "eventId": "evt-complete-001",
            }
        )
        await analytics_svc.track_event(req, visitor_id="visitor-1")

        learner_svc = LearnerStateService(session)
        completed = await learner_svc.get_completed_lessons("visitor-1")
        assert "polars-basics" in completed


@pytest.mark.anyio
async def test_code_run_event_linkage(test_engine):
    """code_run 事件应联动记录 attempt"""
    async for session in _standalone_session(test_engine):
        analytics_svc = AnalyticsService(session)

        await analytics_svc.track_event(
            EventTrackRequest.model_validate(
                {
                    "eventType": "code_run",
                    "lessonSlug": "polars-basics",
                    "eventId": "evt-run-001",
                    "status": "success",
                }
            ),
            visitor_id="visitor-1",
        )
        await analytics_svc.track_event(
            EventTrackRequest.model_validate(
                {
                    "eventType": "code_run",
                    "lessonSlug": "polars-basics",
                    "eventId": "evt-run-002",
                    "status": "error",
                }
            ),
            visitor_id="visitor-1",
        )

        learner_svc = LearnerStateService(session)
        detail = await learner_svc.get_lesson_progress("visitor-1", "polars-basics")
        assert detail is not None
        assert detail.attempt_count == 2
        assert detail.success_count == 1
        assert detail.error_count == 1


@pytest.mark.anyio
async def test_lesson_uncomplete_event_linkage(test_engine):
    """lesson_uncomplete 事件应联动撤销 LearnerState"""
    async for session in _standalone_session(test_engine):
        analytics_svc = AnalyticsService(session)

        # 先完成
        await analytics_svc.track_event(
            EventTrackRequest.model_validate(
                {
                    "eventType": "lesson_complete",
                    "lessonSlug": "polars-basics",
                    "eventId": "evt-complete-002",
                }
            ),
            visitor_id="visitor-1",
        )
        # 再撤销
        await analytics_svc.track_event(
            EventTrackRequest.model_validate(
                {
                    "eventType": "lesson_uncomplete",
                    "lessonSlug": "polars-basics",
                    "eventId": "evt-uncomplete-001",
                }
            ),
            visitor_id="visitor-1",
        )

        learner_svc = LearnerStateService(session)
        completed = await learner_svc.get_completed_lessons("visitor-1")
        assert "polars-basics" not in completed


@pytest.mark.anyio
async def test_code_save_recorded_with_snapshot_in_same_transaction(test_engine):
    """保存快照时应同事务记录 code_save 事件"""
    from sqlalchemy import select

    async for session in _standalone_session(test_engine):
        analytics_svc = AnalyticsService(session)

        resp = await analytics_svc.save_snapshot(
            CodeSnapshotRequest.model_validate(
                {
                    "lessonSlug": "polars-basics",
                    "code": "print('hello')",
                    "language": "python",
                }
            ),
            visitor_id="visitor-snap",
        )
        assert resp.snapshot_id > 0

        # 应存在一条 code_save 事件，关联同一课程
        stmt = select(LearningRecord).where(
            LearningRecord.visitor_id == "visitor-snap",
            LearningRecord.event_type == "code_save",
            LearningRecord.is_deleted == False,  # noqa: E712
        )
        result = await session.execute(stmt)
        records = list(result.scalars().all())
        assert len(records) == 1
        assert records[0].lesson_slug == "polars-basics"


@pytest.mark.anyio
async def test_ai_help_recorded_by_agent_chat_endpoint(test_engine):
    """Agent chat 成功受理后应记录 ai_help 事件（visitor_id 由 session 注入）"""
    from httpx import ASGITransport, AsyncClient

    from app.core import get_anonymous_visitor_id
    from app.core.database.database import get_db
    from main import app

    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    session = factory()

    async def override_get_db():
        yield session

    visitor_id = "visitor-aihelp"
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_anonymous_visitor_id] = lambda: visitor_id
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as api_client:
            resp = await api_client.post(
                "/api/v1/agent/chat",
                json={
                    "message": "这节课的核心知识点是什么？",
                    "history": [],
                    "context": {"currentLesson": "polars-basics"},
                },
            )
            assert resp.status_code == 200

            # 无服务端练习证据时，ai_help 只计入用户画像，不接受客户端
            # currentLesson 作为课程归属事实。
            profile_resp = await api_client.get("/api/v1/analytics/user-profile")
            assert profile_resp.status_code == 200
            assert profile_resp.json()["data"]["aiHelps"] == 1

            stats_resp = await api_client.get("/api/v1/analytics/user-lesson-stats")
            assert stats_resp.status_code == 200
            details = stats_resp.json()["data"].get("lessonDetails", [])
            assert all(d["slug"] != "polars-basics" for d in details)
    finally:
        app.dependency_overrides.clear()
        await session.close()
