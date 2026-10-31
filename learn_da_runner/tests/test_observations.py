import json
import sys

from runner.local_provider import LocalSubprocessProvider
from runner.schemas import RunnerSessionRequest
from runner.session import build_driver_input
from runner.session import _safe_relative, SessionWorkspaceError
from runner.main import build_provider
from runner.settings import runner_settings
import pytest


def test_observation_mode_returns_values_and_calls_without_expectations():
    request = RunnerSessionRequest(requestId="22222222-2222-2222-2222-222222222222",
        cells=[{"cellId": "c1", "code": "x=7\ndef bonus(n): return n+5"}],
        observationMode=True,
        assertions=[{"id": "a", "type": "value", "var": "x"},
                    {"id": "b", "type": "call", "function": "bonus", "args": [95]}])
    payload = json.loads(build_driver_input(request, "nonce"))
    assert payload["observationMode"] is True
    result = LocalSubprocessProvider(python_executable=sys.executable).execute_session(request)
    events = result["observations"]
    assert any(e.get("t") == "vars" and e["vars"]["x"]["data"] == "7" for e in events)
    assert any(e.get("t") == "call" and e["value"]["data"] == "100" for e in events)
    assert result["assertions"] == []


def test_custom_value_observation_is_unsupported():
    request = RunnerSessionRequest(requestId="22222222-2222-2222-2222-222222222222",
        cells=[{"cellId": "c1", "code": "class L(list): pass\nx=L([1])"}],
        observationMode=True, assertions=[{"id": "a", "type": "value", "var": "x"}])
    result = LocalSubprocessProvider(python_executable=sys.executable).execute_session(request)
    values = next(e["vars"] for e in result["observations"] if e.get("t") == "vars")
    assert values["x"]["kind"] == "unsupported"


def test_observation_payload_larger_than_console_limit_is_not_truncated():
    request = RunnerSessionRequest(requestId="22222222-2222-2222-2222-222222222222",
        cells=[{"cellId": "c1", "code": "x='a'*100000"}], observationMode=True,
        assertions=[{"id": "a", "type": "value", "var": "x"}])
    result = LocalSubprocessProvider(python_executable=sys.executable).execute_session(request)
    assert result["status"] == "success", result
    values = next(e["vars"] for e in result["observations"] if e.get("t") == "vars")
    assert len(json.loads(values["x"]["data"])) == 100000


def test_driver_output_is_ascii_safe_for_docker_log_chunk_boundaries(tmp_path):
    import subprocess
    from runner.session import prepare_workspace, frame_driver_input
    request = RunnerSessionRequest(requestId="22222222-2222-2222-2222-222222222222",
        cells=[{"cellId": "c1", "code": "x='华'*30000"}], observationMode=True,
        assertions=[{"id": "a", "type": "value", "var": "x"}])
    prepare_workspace(tmp_path, request)
    result = subprocess.run([sys.executable, "driver.py"], cwd=tmp_path,
                            input=frame_driver_input(request, "nonce"), capture_output=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout.isascii()


@pytest.mark.parametrize("path", ["C:escape.csv", "D:/escape.csv", "\\\\host\\share\\x"])
def test_windows_drive_paths_are_rejected(path):
    with pytest.raises(SessionWorkspaceError):
        _safe_relative(path)


@pytest.mark.parametrize("environment", ["", "staging", "prod", "production"])
def test_local_execution_requires_known_development_environment(monkeypatch, environment):
    monkeypatch.setattr(runner_settings, "RUNNER_PROVIDER", "local")
    monkeypatch.setattr(runner_settings, "RUNNER_ALLOW_LOCAL_EXECUTION", True)
    monkeypatch.setattr(runner_settings, "RUNNER_ENV", environment)
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(RuntimeError):
        build_provider()


def test_local_development_setting_cannot_override_production_app_env(monkeypatch):
    monkeypatch.setattr(runner_settings, "RUNNER_PROVIDER", "local")
    monkeypatch.setattr(runner_settings, "RUNNER_ALLOW_LOCAL_EXECUTION", True)
    monkeypatch.setattr(runner_settings, "RUNNER_ENV", "development")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        build_provider()
