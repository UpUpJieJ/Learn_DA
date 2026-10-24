"""RunnerClient unit tests using httpx.MockTransport."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from app.sandbox.client import RunnerClient, RunnerUnavailableError
from app.sandbox.schemas import RunnerExecutionRequest

REQUEST_ID = UUID("00000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000002")

FAKE_SETTINGS = SimpleNamespace(
    RUNNER_URL="http://runner:8080",
    RUNNER_TOKEN="t" * 32,
    RUNNER_TIMEOUT_SECONDS=7.0,
    RUNNER_SESSION_TIMEOUT_SECONDS=30.0,
)


def valid_request() -> RunnerExecutionRequest:
    return RunnerExecutionRequest(
        request_id=REQUEST_ID,
        code="print('ok')",
        source="playground",
    )


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_runner_success_deserialization():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "requestId": str(REQUEST_ID),
                "executionId": str(EXECUTION_ID),
                "status": "success",
                "stdout": "ok\n",
                "stderr": "",
                "errorType": None,
                "durationMs": 12,
                "outputTruncated": False,
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    result = await client.execute(valid_request())

    assert result.status == "success"
    assert result.request_id == REQUEST_ID
    assert result.execution_id == EXECUTION_ID
    assert result.stdout == "ok\n"
    assert result.duration_ms == 12

    await http.aclose()


# ---------------------------------------------------------------------------
# Failure paths → RunnerUnavailableError
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_runner_connect_timeout_is_unavailable():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    with pytest.raises(RunnerUnavailableError, match="runner unavailable"):
        await client.execute(valid_request())

    await http.aclose()


@pytest.mark.unit
async def test_runner_malformed_response_is_unavailable():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    with pytest.raises(RunnerUnavailableError, match="runner unavailable"):
        await client.execute(valid_request())

    await http.aclose()


@pytest.mark.unit
async def test_runner_503_is_unavailable():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "Docker provider unhealthy"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    with pytest.raises(RunnerUnavailableError, match="runner unavailable"):
        await client.execute(valid_request())

    await http.aclose()


@pytest.mark.unit
async def test_exception_does_not_leak_code_or_response_body():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="secret internal error")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    with pytest.raises(RunnerUnavailableError) as exc_info:
        await client.execute(valid_request())

    assert "print('ok')" not in str(exc_info.value)
    assert "secret internal error" not in str(exc_info.value)

    await http.aclose()


# ---------------------------------------------------------------------------
# Session replay (workspace M1/M2)
# ---------------------------------------------------------------------------


def _captured_timeout(request: httpx.Request) -> float:
    timeout = request.extensions.get("timeout") or {}
    return float(timeout.get("read") or timeout.get("connect") or 0.0)


@pytest.mark.unit
async def test_session_posts_to_sessions_endpoint_and_returns_payload():
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"verdict": "passed", "cells": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    result = await client.execute_session({"requestId": str(REQUEST_ID), "cells": []})

    assert result == {"verdict": "passed", "cells": []}
    assert str(seen[0].url) == "http://runner:8080/v1/sessions"
    assert seen[0].headers["X-Runner-Token"] == "t" * 32

    await http.aclose()


@pytest.mark.unit
async def test_session_uses_the_dedicated_session_timeout():
    """整段重放必须用 RUNNER_SESSION_TIMEOUT_SECONDS，不能退回单格超时。"""
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"verdict": "passed"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    await client.execute_session({"cells": []})

    assert _captured_timeout(seen[0]) == 30.0

    await http.aclose()


@pytest.mark.unit
async def test_session_timeout_follows_injected_settings_not_global_settings():
    """回归：旧实现用 getattr(settings, ...) 读全局 settings，注入的替身被静默忽略。"""
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"verdict": "passed"})

    injected = SimpleNamespace(
        RUNNER_URL="http://runner:8080",
        RUNNER_TOKEN="t" * 32,
        RUNNER_TIMEOUT_SECONDS=7.0,
        RUNNER_SESSION_TIMEOUT_SECONDS=45.0,
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, injected)

    await client.execute_session({"cells": []})

    assert _captured_timeout(seen[0]) == 45.0

    await http.aclose()


@pytest.mark.unit
async def test_session_timeout_falls_back_to_single_cell_timeout():
    """替身没有该字段时回落到单格超时，而不是硬编码常数。"""
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"verdict": "passed"})

    injected = SimpleNamespace(
        RUNNER_URL="http://runner:8080",
        RUNNER_TOKEN="t" * 32,
        RUNNER_TIMEOUT_SECONDS=7.0,
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, injected)

    await client.execute_session({"cells": []})

    assert _captured_timeout(seen[0]) == 7.0

    await http.aclose()


@pytest.mark.unit
async def test_session_503_is_unavailable():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "unhealthy"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    with pytest.raises(RunnerUnavailableError, match="runner unavailable"):
        await client.execute_session({"cells": []})

    await http.aclose()


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_is_ready_returns_true_on_200():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ready"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    assert await client.is_ready() is True

    await http.aclose()


@pytest.mark.unit
async def test_is_ready_returns_false_on_503():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "unhealthy"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    assert await client.is_ready() is False

    await http.aclose()


@pytest.mark.unit
async def test_is_ready_returns_false_on_connection_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = RunnerClient(http, FAKE_SETTINGS)

    assert await client.is_ready() is False

    await http.aclose()
