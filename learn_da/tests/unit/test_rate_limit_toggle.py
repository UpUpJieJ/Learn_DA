"""RATE_LIMIT_ENABLED 必须真正关掉按路由的限流（2026-10-21 回归）。

曾经的问题：`RATE_LIMIT_ENABLED=False` 只跳过 `setup_limiter_middleware()`，
而各路由上的 `@limiter.limit(...)` 装饰器仍独立计数并抛 429 —— 于是"关掉限流"
再跑全量练习，第 11 次请求直接 429（当时 `scripts/verify_exercises.py` 的文档因此失效；
该脚本已随练习链路下线，现由 `scripts/verify_workspace.py` 承担）。
"""

from unittest.mock import AsyncMock

import pytest

from app.sandbox import schemas as sandbox_schemas
from app.utils.limiter import limiter
from config.settings import settings

REQUEST_ID = "11111111-1111-1111-1111-111111111111"
EXECUTION_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def clear_limiter():
    """每个用例前后清空计数，避免污染其他会打同一路由的测试。"""
    limiter.reset()
    yield
    limiter.reset()


def test_limiter_enabled_mirrors_settings():
    """Limiter 的 enabled 标志必须与 RATE_LIMIT_ENABLED 一致（导入期同步）。"""
    assert limiter.enabled is bool(settings.RATE_LIMIT_ENABLED)


@pytest.mark.unit
async def test_disabled_limiter_lets_requests_through(client, monkeypatch, clear_limiter):
    """关掉限流后，超过单路由配额的请求不应再被 429 拦下。"""
    from main import app

    app.state.runner_client.execute = AsyncMock(
        return_value=sandbox_schemas.SandboxExecutionResult(
            request_id=REQUEST_ID,
            execution_id=EXECUTION_ID,
            status="success",
            stdout="1\n",
            duration_ms=1,
        )
    )
    monkeypatch.setattr(limiter, "enabled", False)

    for _ in range(12):  # RATE_LIMIT_PLAYGROUND_EXECUTE 默认 10/minute
        response = await client.post(
            "/api/v1/playground/execute",
            json={"code": "print(1)", "language": "python"},
        )
        assert response.status_code != 429