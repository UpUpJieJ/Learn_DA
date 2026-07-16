"""
Integration tests for snapshot pagination and retention governance.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.models import CodeSnapshot
from app.core.database.database import get_db
from app.core import get_anonymous_visitor_id
from main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.unit
async def test_snapshot_pagination_returns_page(test_engine):
    """Insert 25 snapshots; page 1 (10 items) and page 2 (10 items) should not overlap."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )
    session = async_session()
    visitor_id = "pagination-test-user"

    # Insert 25 snapshots
    for i in range(25):
        session.add(CodeSnapshot(
            visitor_id=visitor_id,
            code=f"print({i})",
            language="python",
            version=i + 1,
        ))
    await session.flush()
    await session.commit()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_anonymous_visitor_id] = lambda: visitor_id

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            resp1 = await client.get(
                "/api/v1/analytics/snapshots",
                params={"page": 1, "page_size": 10},
            )
            assert resp1.status_code == 200
            data1 = resp1.json()["data"]
            assert data1["total"] == 25
            assert len(data1["items"]) == 10
            assert data1["page"] == 1

            resp2 = await client.get(
                "/api/v1/analytics/snapshots",
                params={"page": 2, "page_size": 10},
            )
            assert resp2.status_code == 200
            data2 = resp2.json()["data"]
            assert len(data2["items"]) == 10
            assert data2["page"] == 2

            # Pages should not overlap
            ids1 = {item["id"] for item in data1["items"]}
            ids2 = {item["id"] for item in data2["items"]}
            assert ids1.isdisjoint(ids2)

            # Page 3 should have remaining 5
            resp3 = await client.get(
                "/api/v1/analytics/snapshots",
                params={"page": 3, "page_size": 10},
            )
            data3 = resp3.json()["data"]
            assert len(data3["items"]) == 5
    finally:
        app.dependency_overrides.clear()
        await session.close()


@pytest.mark.unit
async def test_snapshot_retention_prunes_excess(test_engine):
    """Insert 105 snapshots for a session, save one more — total should be <= 100."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )
    session = async_session()
    visitor_id = "retention-test-user"

    # Insert 105 snapshots directly
    for i in range(105):
        session.add(CodeSnapshot(
            visitor_id=visitor_id,
            code=f"print({i})",
            language="python",
            version=i + 1,
        ))
    await session.flush()
    await session.commit()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_anonymous_visitor_id] = lambda: visitor_id

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            # Save one more snapshot via API — triggers prune
            resp = await client.post(
                "/api/v1/analytics/snapshot",
                json={"code": "print('new')", "language": "python"},
            )
            assert resp.status_code == 200

            # Check that total non-deleted snapshots is <= 100
            resp_list = await client.get(
                "/api/v1/analytics/snapshots",
                params={"page": 1, "page_size": 1},
            )
            data = resp_list.json()["data"]
            assert data["total"] <= 100
    finally:
        app.dependency_overrides.clear()
        await session.close()


@pytest.mark.unit
async def test_snapshot_page_default_params(test_engine):
    """Default page=1, page_size=20 should work."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )
    session = async_session()
    visitor_id = "default-page-user"

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_anonymous_visitor_id] = lambda: visitor_id

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/analytics/snapshots")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["page"] == 1
            assert data["pageSize"] == 20
            assert data["total"] == 0
            assert data["items"] == []
    finally:
        app.dependency_overrides.clear()
        await session.close()
