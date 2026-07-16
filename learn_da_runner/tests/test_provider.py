"""Docker execution provider policy tests.

All tests mock the Docker SDK — no real Docker daemon is required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from runner.provider import DockerExecutionProvider
from runner.schemas import RunnerExecutionRequest

REQUEST_ID = UUID("00000000-0000-0000-0000-000000000001")
IMAGE = "polars-duckdb-sandbox:latest"


def make_request(code: str = "print('ok')", source: str = "playground") -> RunnerExecutionRequest:
    return RunnerExecutionRequest(request_id=REQUEST_ID, code=code, source=source)


def make_container_mock(
    *,
    exit_code: int = 0,
    stdout: str = "ok\n",
    stderr: str = "",
    timeout: bool = False,
) -> MagicMock:
    """Return a mock DockerClient whose containers.run behaves as configured."""
    client = MagicMock()
    container = MagicMock()
    container.wait.return_value = {"StatusCode": exit_code}

    if timeout:
        container.wait.side_effect = Exception("timeout")

    # Docker SDK container.logs() returns bytes when not streaming.
    container.logs.return_value = stdout.encode() if stdout else b""

    client.containers.run.return_value = container
    return client


# ---------------------------------------------------------------------------
# Security constraints
# ---------------------------------------------------------------------------


def test_provider_enforces_container_security_constraints():
    """Verify the exact Docker arguments required by the Spec."""
    client = make_container_mock()

    with patch("runner.provider.docker.DockerClient", return_value=client):
        provider = DockerExecutionProvider(image=IMAGE)
        provider._client = client  # inject mock
        provider.execute(make_request())

    call_kwargs = client.containers.run.call_args
    assert call_kwargs.kwargs.get("network_mode") == "none"
    assert call_kwargs.kwargs.get("read_only") is True
    assert call_kwargs.kwargs.get("user") == "65532:65532"
    assert call_kwargs.kwargs.get("pids_limit") == 64
    assert call_kwargs.kwargs.get("cap_drop") == ["ALL"]
    assert call_kwargs.kwargs.get("security_opt") == ["no-new-privileges"]
    assert call_kwargs.kwargs.get("mem_limit") == "256m"
    assert call_kwargs.kwargs.get("nano_cpus") == 500_000_000
    tmpfs = call_kwargs.kwargs.get("tmpfs", {})
    assert "/tmp" in tmpfs


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------


def test_zero_exit_maps_to_success():
    client = make_container_mock(exit_code=0, stdout="ok\n")
    with patch("runner.provider.docker.DockerClient", return_value=client):
        provider = DockerExecutionProvider(image=IMAGE)
        provider._client = client
        result = provider.execute(make_request())

    assert result["status"] == "success"
    assert result["stdout"] == "ok\n"


def test_nonzero_exit_maps_to_error():
    client = make_container_mock(exit_code=1, stdout="NameError: ...")
    with patch("runner.provider.docker.DockerClient", return_value=client):
        provider = DockerExecutionProvider(image=IMAGE)
        provider._client = client
        result = provider.execute(make_request(code="print(x)"))

    assert result["status"] == "error"
    assert "NameError" in result["stdout"]


def test_timeout_maps_to_timeout_status():
    client = make_container_mock(timeout=True)
    with patch("runner.provider.docker.DockerClient", return_value=client):
        provider = DockerExecutionProvider(image=IMAGE)
        provider._client = client
        result = provider.execute(make_request(code="while True: pass"))

    assert result["status"] == "timeout"


# ---------------------------------------------------------------------------
# Output clipping
# ---------------------------------------------------------------------------


def test_output_is_clipped_to_65536_bytes():
    big_stdout = "x" * 70_000
    client = make_container_mock(exit_code=0, stdout=big_stdout)
    with patch("runner.provider.docker.DockerClient", return_value=client):
        provider = DockerExecutionProvider(image=IMAGE)
        provider._client = client
        result = provider.execute(make_request())

    assert len(result["stdout"]) == 65_536
    assert result["outputTruncated"] is True


def test_small_output_is_not_clipped():
    client = make_container_mock(exit_code=0, stdout="hello\n")
    with patch("runner.provider.docker.DockerClient", return_value=client):
        provider = DockerExecutionProvider(image=IMAGE)
        provider._client = client
        result = provider.execute(make_request())

    assert result["stdout"] == "hello\n"
    assert result["outputTruncated"] is False


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def test_container_is_removed_even_on_error():
    client = make_container_mock(timeout=True)
    with patch("runner.provider.docker.DockerClient", return_value=client):
        provider = DockerExecutionProvider(image=IMAGE)
        provider._client = client
        provider.execute(make_request())

    container = client.containers.run.return_value
    container.remove.assert_called_once_with(force=True)


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------


def test_ping_returns_true_when_docker_is_reachable():
    client = MagicMock()
    client.ping.return_value = True
    with patch("runner.provider.docker.DockerClient", return_value=client):
        provider = DockerExecutionProvider(image=IMAGE)
        provider._client = client
        assert provider.ping() is True


def test_ping_returns_false_when_docker_is_unreachable():
    client = MagicMock()
    client.ping.side_effect = Exception("connection refused")
    with patch("runner.provider.docker.DockerClient", return_value=client):
        provider = DockerExecutionProvider(image=IMAGE)
        provider._client = client
        assert provider.ping() is False
