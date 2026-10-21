"""Local subprocess provider — development escape hatch tests.

These tests run a real host interpreter; they do not need Docker.
"""

from __future__ import annotations

import sys
from uuid import UUID

import pytest

from runner.local_provider import LocalSubprocessProvider
from runner.main import build_provider
from runner.schemas import ExecutionStatus, RunnerExecutionRequest
from runner.settings import runner_settings

REQUEST_ID = UUID("00000000-0000-0000-0000-000000000042")


def make_request(code: str) -> RunnerExecutionRequest:
    return RunnerExecutionRequest(request_id=REQUEST_ID, code=code)


@pytest.fixture()
def provider() -> LocalSubprocessProvider:
    return LocalSubprocessProvider(python_executable=sys.executable, timeout_seconds=10)


def test_ping_reports_healthy(provider: LocalSubprocessProvider) -> None:
    assert provider.ping() is True


def test_ping_reports_unhealthy_for_missing_interpreter() -> None:
    broken = LocalSubprocessProvider(python_executable="definitely-not-a-python-binary")
    assert broken.ping() is False


def test_successful_execution_captures_stdout(provider: LocalSubprocessProvider) -> None:
    result = provider.execute(make_request("print(sum(range(10)))"))

    assert result["status"] == ExecutionStatus.SUCCESS
    assert result["stdout"].strip() == "45"
    assert result["stderr"] == ""
    assert result["errorType"] is None
    assert result["requestId"] == str(REQUEST_ID)
    assert result["durationMs"] >= 0


def test_failing_execution_reports_runtime_error(
    provider: LocalSubprocessProvider,
) -> None:
    result = provider.execute(make_request("raise ValueError('boom')"))

    assert result["status"] == ExecutionStatus.ERROR
    assert result["errorType"] == "runtime_error"
    assert "ValueError: boom" in result["stderr"]


def test_timeout_kills_the_child_process() -> None:
    fast_timeout = LocalSubprocessProvider(
        python_executable=sys.executable, timeout_seconds=1)
    result = fast_timeout.execute(make_request("import time; time.sleep(30)"))

    assert result["status"] == ExecutionStatus.TIMEOUT
    assert result["errorType"] == "timeout"


def test_output_is_clipped(provider: LocalSubprocessProvider) -> None:
    result = provider.execute(
        make_request("print('x' * (200 * 1024))"))

    assert result["outputTruncated"] is True
    assert len(result["stdout"].encode("utf-8")) <= runner_settings.RUNNER_MAX_OUTPUT_BYTES


def test_newlines_match_linux_sandbox(provider: LocalSubprocessProvider) -> None:
    result = provider.execute(make_request("print('a'); print('b')"))

    assert result["stdout"] == "a\nb\n"
    assert "\r" not in result["stdout"]


def test_child_does_not_inherit_secrets(
    provider: LocalSubprocessProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEARN_DA_TEST_SECRET", "leaked")
    result = provider.execute(
        make_request("import os; print(os.environ.get('LEARN_DA_TEST_SECRET', 'absent'))"))

    assert result["stdout"].strip() == "absent"


# ---------------------------------------------------------------------------
# Provider selection guards
# ---------------------------------------------------------------------------


def test_local_provider_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner_settings, "RUNNER_PROVIDER", "local")
    monkeypatch.setattr(runner_settings, "RUNNER_ALLOW_LOCAL_EXECUTION", False)

    with pytest.raises(RuntimeError, match="RUNNER_ALLOW_LOCAL_EXECUTION"):
        build_provider()


def test_local_provider_refused_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner_settings, "RUNNER_PROVIDER", "local")
    monkeypatch.setattr(runner_settings, "RUNNER_ALLOW_LOCAL_EXECUTION", True)
    monkeypatch.setattr(runner_settings, "RUNNER_ENV", "production")

    with pytest.raises(RuntimeError, match="refused in production"):
        build_provider()


def test_local_provider_allowed_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner_settings, "RUNNER_PROVIDER", "local")
    monkeypatch.setattr(runner_settings, "RUNNER_ALLOW_LOCAL_EXECUTION", True)
    monkeypatch.setattr(runner_settings, "RUNNER_ENV", "development")

    assert isinstance(build_provider(), LocalSubprocessProvider)


def test_unknown_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_settings, "RUNNER_PROVIDER", "jail")

    with pytest.raises(RuntimeError, match="Unknown RUNNER_PROVIDER"):
        build_provider()