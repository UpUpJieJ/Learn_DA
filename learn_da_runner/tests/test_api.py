"""API authentication and contract tests for the Runner service."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runner.main import app, get_provider


class FakeProvider:
    """In-memory provider that returns a well-formed success result."""

    def ping(self) -> bool:
        return True

    def execute(self, request):
        return {
            "requestId": str(request.request_id),
            "executionId": "00000000-0000-0000-0000-000000000002",
            "status": "success",
            "stdout": "ok\n",
            "stderr": "",
            "errorType": None,
            "durationMs": 2,
            "outputTruncated": False,
        }


class UnhealthyProvider(FakeProvider):
    """Provider whose Docker backend is unreachable."""

    def ping(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_execute_requires_runner_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/executions",
                json={
                    "requestId": "00000000-0000-0000-0000-000000000001",
                    "code": "print('ok')",
                    "language": "python",
                    "source": "playground",
                },
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_execute_rejects_wrong_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/executions",
                headers={"X-Runner-Token": "wrong-token"},
                json={
                    "requestId": "00000000-0000-0000-0000-000000000001",
                    "code": "print('ok')",
                    "language": "python",
                    "source": "playground",
                },
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_execute_returns_stable_contract(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/executions",
                headers={"X-Runner-Token": "t" * 32},
                json={
                    "requestId": "00000000-0000-0000-0000-000000000001",
                    "code": "print('ok')",
                    "language": "python",
                    "source": "playground",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["requestId"] == "00000000-0000-0000-0000-000000000001"
        assert body["executionId"] == "00000000-0000-0000-0000-000000000002"
        assert body["stdout"] == "ok\n"
        assert body["stderr"] == ""
        assert body["errorType"] is None
        assert body["durationMs"] == 2
        assert body["outputTruncated"] is False
    finally:
        app.dependency_overrides.clear()


def test_execute_accepts_agent_suggested_source(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/executions",
                headers={"X-Runner-Token": "t" * 32},
                json={
                    "requestId": "00000000-0000-0000-0000-000000000001",
                    "code": "print(1)",
                    "language": "python",
                    "source": "agent_suggested",
                },
            )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_execute_rejects_invalid_source(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/executions",
                headers={"X-Runner-Token": "t" * 32},
                json={
                    "requestId": "00000000-0000-0000-0000-000000000001",
                    "code": "print(1)",
                    "language": "python",
                    "source": "operator",
                },
            )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


def test_liveness_always_returns_200(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: UnhealthyProvider()
    try:
        with TestClient(app) as client:
            response = client.get("/live")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_readiness_returns_503_when_provider_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: UnhealthyProvider()
    try:
        with TestClient(app) as client:
            response = client.get("/ready")
        assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_readiness_returns_200_when_healthy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    try:
        with TestClient(app) as client:
            response = client.get("/ready")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
