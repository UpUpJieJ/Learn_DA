"""
核心接口 smoke 测试
"""

import pytest

from config.settings import settings


@pytest.mark.unit
async def test_health_check_success(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["app"] == "healthy"
    assert body["data"]["database"] == "healthy"
    assert body["data"]["redis"] == "disabled"


@pytest.mark.unit
async def test_root_returns_project_metadata(client):
    resp = await client.get("/")
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["name"] == "Learn DA Backend"
    assert "learning" in body["data"]["enabledModules"]


@pytest.mark.unit
async def test_lessons_endpoint(client):
    resp = await client.get("/api/v1/lessons")
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert len(body["data"]) >= 1


@pytest.mark.unit
async def test_playground_execute_returns_mock_result(client, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_DOCKER_ENABLED", False)
    monkeypatch.setattr(settings, "SANDBOX_LOCAL_ENABLED", False)
    resp = await client.post(
        "/api/v1/playground/execute",
        json={"code": "import polars as pl\nprint('ok')"},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["usedSandbox"] == "mock"
    assert body["data"]["status"] == "mocked"


@pytest.mark.unit
async def test_agent_chat_uses_learning_toolchain(client):
    resp = await client.post(
        "/api/v1/agent/chat",
        json={"message": "给我一个 duckdb 示例"},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["toolName"] == "generate_example_code"


@pytest.mark.unit
async def test_agent_chat_accepts_history_and_context(client):
    resp = await client.post(
        "/api/v1/agent/chat",
        json={
            "message": "这个报错怎么修？",
            "history": [{"role": "user", "content": "我在学 Polars"}],
            "context": {
                "currentCode": "import polars as pl\nprint(df)",
                "lastError": "NameError: name 'df' is not defined",
            },
        },
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["toolName"] == "fix_code"
    assert body["data"]["content"]
    assert "model" in body["data"]


@pytest.mark.unit
async def test_agent_fix_returns_structured_fallback(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    resp = await client.post(
        "/api/v1/agent/fix",
        json={
            "code": "print(df)",
            "errorMessage": "NameError: name 'df' is not defined",
        },
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert "fixedCode" in body["data"]
    assert "explanation" in body["data"]
    assert body["data"]["usedFallback"] is True
    assert body["data"]["verification"] is None


@pytest.mark.unit
async def test_agent_explain_returns_structured_fallback(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    resp = await client.post(
        "/api/v1/agent/explain",
        json={"code": "import polars as pl\nprint('ok')"},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["explanation"]
    assert body["data"]["usedFallback"] is True
