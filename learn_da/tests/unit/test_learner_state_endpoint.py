"""
阶段 1：统一学习事实 - Learner State HTTP 契约测试

补齐此前缺失的端点层覆盖。之前 learner_state 只有 service 层测试，导致
`.env` 里 ENABLED_APP_MODULES 漏配 learner_state（路由根本没注册、线上全 404）
这类问题无法被测试发现。

覆盖场景：
- learner_state 模块处于启用列表中（路由注册的前置条件）
- GET /learner-state/progress 可达且返回权威投影
- 事件上报 -> 进度投影的端到端链路（写路径唯一走 /analytics/track）
- learner_state 不暴露任何写端点（防止双写路径回潮）
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import get_anonymous_visitor_id
from app.core.database.database import get_db
from config.settings import settings
from main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _client_with_session(test_engine, visitor_id: str):
    """构造带独立 session 的测试客户端（service 内部会 commit）。"""
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    session = factory()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_anonymous_visitor_id] = lambda: visitor_id
    return session


@pytest.mark.unit
def test_learner_state_module_is_enabled():
    """learner_state 必须在启用模块列表里，否则所有 learner-state 路由都不会注册。"""
    assert "learner_state" in settings.enabled_app_modules


@pytest.mark.unit
def test_learner_state_exposes_no_write_endpoints():
    """写路径唯一走 /analytics/track：learner-state 只允许存在读端点。"""
    write_routes = [
        (route.path, sorted(route.methods))
        for route in app.routes
        if getattr(route, "path", "").startswith(f"{settings.API_PREFIX}/learner-state")
        and getattr(route, "methods", set()) - {"GET", "HEAD", "OPTIONS"}
    ]
    assert write_routes == [], f"learner-state 不应有写端点: {write_routes}"


@pytest.mark.anyio
async def test_progress_endpoint_is_reachable(test_engine):
    """GET /learner-state/progress 应可达并返回空投影（而不是 404）。"""
    session = await _client_with_session(test_engine, "visitor-progress-empty")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as api_client:
            resp = await api_client.get("/api/v1/learner-state/progress")
            assert resp.status_code == 200

            data = resp.json()["data"]
            assert data["completedLessons"] == []
            assert data["lastVisitedSlug"] is None
            assert data["totalCompleted"] == 0
            assert data["totalStarted"] == 0
    finally:
        app.dependency_overrides.clear()
        await session.close()


@pytest.mark.anyio
async def test_track_event_drives_progress_projection(test_engine):
    """事件上报是唯一写路径：track -> progress 端到端反映完成状态与最近访问。"""
    visitor_id = "visitor-progress-e2e"
    session = await _client_with_session(test_engine, visitor_id)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as api_client:
            for payload in (
                {
                    "eventType": "lesson_start",
                    "lessonSlug": "polars-basics",
                    "eventId": "e2e-start-1",
                },
                {
                    "eventType": "lesson_complete",
                    "lessonSlug": "polars-basics",
                    "eventId": "e2e-complete-1",
                },
                {
                    "eventType": "lesson_start",
                    "lessonSlug": "duckdb-analytics",
                    "eventId": "e2e-start-2",
                },
            ):
                resp = await api_client.post("/api/v1/analytics/track", json=payload)
                assert resp.status_code == 200, resp.text

            data = (await api_client.get("/api/v1/learner-state/progress")).json()[
                "data"
            ]
            assert data["completedLessons"] == ["polars-basics"]
            assert data["totalCompleted"] == 1
            assert data["totalStarted"] == 2
            # 最近一次活动是 duckdb-analytics
            assert data["lastVisitedSlug"] == "duckdb-analytics"

            statuses = {d["lessonSlug"]: d["status"] for d in data["lessonDetails"]}
            assert statuses["polars-basics"] == "completed"
            assert statuses["duckdb-analytics"] == "started"
    finally:
        app.dependency_overrides.clear()
        await session.close()


@pytest.mark.anyio
async def test_code_run_status_is_persisted_verbatim(test_engine):
    """错误类型必须可聚合：timeout / rejected 不能被归并成 error 后再落库。"""
    from sqlalchemy import select

    from app.analytics.models import LearningRecord

    visitor_id = "visitor-status-fidelity"
    session = await _client_with_session(test_engine, visitor_id)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as api_client:
            for idx, status in enumerate(
                ("success", "error", "timeout", "rejected", "unavailable")
            ):
                resp = await api_client.post(
                    "/api/v1/analytics/track",
                    json={
                        "eventType": "code_run",
                        "lessonSlug": "polars-basics",
                        "eventId": f"e2e-status-{idx}",
                        "status": status,
                    },
                )
                assert resp.status_code == 200, resp.text

            rows = (
                await session.execute(
                    select(LearningRecord.status).where(
                        LearningRecord.visitor_id == visitor_id,
                        LearningRecord.event_type == "code_run",
                        LearningRecord.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalars()
            assert sorted(rows) == [
                "error",
                "rejected",
                "success",
                "timeout",
                "unavailable",
            ]

            # 投影侧仍按 success 与否二分计数
            data = (await api_client.get("/api/v1/learner-state/progress")).json()[
                "data"
            ]
            detail = next(
                d for d in data["lessonDetails"] if d["lessonSlug"] == "polars-basics"
            )
            assert detail["attemptCount"] == 5
            assert detail["successCount"] == 1
            assert detail["errorCount"] == 4
    finally:
        app.dependency_overrides.clear()
        await session.close()


@pytest.mark.anyio
async def test_replayed_event_does_not_change_projection(test_engine):
    """相同 event_id 重放不改变投影（前端离线重试队列依赖这一点）。"""
    visitor_id = "visitor-progress-replay"
    session = await _client_with_session(test_engine, visitor_id)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as api_client:
            payload = {
                "eventType": "code_run",
                "lessonSlug": "polars-basics",
                "eventId": "e2e-run-dedupe",
                "status": "success",
            }
            for _ in range(3):
                resp = await api_client.post("/api/v1/analytics/track", json=payload)
                assert resp.status_code == 200, resp.text

            data = (await api_client.get("/api/v1/learner-state/progress")).json()[
                "data"
            ]
            detail = next(
                d for d in data["lessonDetails"] if d["lessonSlug"] == "polars-basics"
            )
            assert detail["attemptCount"] == 1
            assert detail["successCount"] == 1
    finally:
        app.dependency_overrides.clear()
        await session.close()
