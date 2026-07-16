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
