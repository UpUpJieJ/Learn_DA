"""
Tests for signed anonymous session cookie.

Step 1: Cookie creation and tamper detection.
Step 4: Cross-session isolation.
"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.unit
async def test_session_cookie_not_secure_on_plain_http(client):
    """明文 HTTP 环境（PUBLIC_SCHEME=http）cookie 不得携带 Secure。

    生产验收发现：Secure cookie 在明文 HTTP 下被浏览器拒收，
    导致匿名访客身份逐请求丢失（进度/Attempt/反馈全部断链）。
    """
    from config.settings import settings

    assert settings.PUBLIC_SCHEME == "http"
    response = await client.get("/api/v1/analytics/user-profile")
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "learn_da_session=" in set_cookie
    assert "secure" not in set_cookie.lower()


@pytest.mark.unit
def test_public_scheme_validator_rejects_invalid_value():
    """PUBLIC_SCHEME 只接受 http/https，防止配错导致 cookie 行为异常。"""
    from pydantic import ValidationError

    from config.settings import Settings

    with pytest.raises(ValidationError):
        Settings(PUBLIC_SCHEME="ftp", CORS_ORIGINS="http://localhost")


@pytest.mark.unit
async def test_first_request_creates_session_cookie(client):
    """A request without a cookie should receive a signed session cookie."""
    response = await client.get("/api/v1/analytics/user-profile")
    assert response.status_code == 200
    # Session cookie should be set in the response
    cookies = response.cookies
    assert "learn_da_session" in cookies


@pytest.mark.unit
async def test_session_cookie_provides_stable_visitor_id(client):
    """Reusing the session cookie should return the same visitor ID."""
    # First request — creates session
    response1 = await client.get("/api/v1/analytics/user-profile")
    assert response1.status_code == 200
    data1 = response1.json()

    # Second request with same cookie jar — same visitor ID
    response2 = await client.get("/api/v1/analytics/user-profile")
    assert response2.status_code == 200
    data2 = response2.json()

    # The visitor ID should be stable (same data returned for same visitor)
    assert data1["data"] == data2["data"]


@pytest.mark.unit
async def test_tampered_cookie_creates_new_identity(client):
    """Modifying the session cookie should result in a new visitor identity."""
    # First request — creates session
    response1 = await client.get("/api/v1/analytics/user-profile")
    assert response1.status_code == 200

    # Get the session cookie and tamper with it
    original_cookie = client.cookies.get("learn_da_session")
    assert original_cookie is not None

    # Create a tampered cookie by modifying bytes
    tampered = original_cookie[:-3] + "abc"
    client.cookies.set("learn_da_session", tampered)

    # Request with tampered cookie should get a new identity
    response2 = await client.get("/api/v1/analytics/user-profile")
    assert response2.status_code == 200

    # A new session cookie should have been set (replacing the tampered one)
    new_cookie = response2.cookies.get("learn_da_session")
    if new_cookie:
        assert new_cookie != tampered


@pytest.mark.unit
async def test_cross_session_isolation(db_session, test_engine):
    """Two independent sessions should have isolated visitor IDs."""
    from httpx import ASGITransport, AsyncClient as HttpxAsyncClient
    from main import app
    from app.core.database.database import get_db
    from unittest.mock import AsyncMock
    from app.sandbox.client import RunnerClient

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    mock_client = AsyncMock(spec=RunnerClient)
    mock_client.is_ready = AsyncMock(return_value=True)
    app.state.runner_client = mock_client

    try:
        # Session A
        async with HttpxAsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client_a:
            response_a = await client_a.get("/api/v1/analytics/user-profile")
            assert response_a.status_code == 200

            # Session B (separate client = separate cookie jar)
            async with HttpxAsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client_b:
                response_b = await client_b.get("/api/v1/analytics/user-profile")
                assert response_b.status_code == 200

                # Each client has its own session cookie
                cookie_a = client_a.cookies.get("learn_da_session")
                cookie_b = client_b.cookies.get("learn_da_session")
                assert cookie_a is not None
                assert cookie_b is not None
                assert cookie_a != cookie_b
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_event_track_no_longer_requires_visitor_id_in_body(client):
    """EventTrackRequest should not require visitorId in the request body."""
    # Post without visitorId in body — should succeed
    response = await client.post(
        "/api/v1/analytics/track",
        json={
            "eventType": "lesson_start",
            "lessonSlug": "python-basics",
            "durationSeconds": 30,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["recorded"] is True
