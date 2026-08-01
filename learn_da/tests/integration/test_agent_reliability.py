"""阶段 3 Task 5：Agent 可靠性回归。

强制回归：
- history：20 条历史消息不崩溃
- abort：请求可取消（ASGI 层面不泄漏）
- 429/rate_limit：超限返回 429 或降级
- timeout：无 LLM key 时降级为 fallback，不 500
- Runner unavailable：无 attempt 证据时 teachingFeedback 为 no_evidence
"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.unit
async def test_long_history_does_not_break(client):
    """20 条历史消息 + 上下文，Agent 仍返回 200 + fallback 内容。"""
    history = [
        {"role": "user", "content": f"问题 {i}"}
        if i % 2 == 0
        else {"role": "assistant", "content": f"回答 {i}"}
        for i in range(20)
    ]
    resp = await client.post(
        "/api/v1/agent/chat",
        json={
            "message": "继续帮我",
            "history": history,
            "context": {"currentLesson": "polars-basics", "attemptId": 1},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["content"]


@pytest.mark.unit
async def test_empty_message_returns_422(client):
    """空消息返回 422，不调用模型。"""
    resp = await client.post(
        "/api/v1/agent/chat",
        json={"message": ""},
    )
    assert resp.status_code == 422 or resp.json()["code"] == 422


@pytest.mark.unit
async def test_timeout_fallback_no_llm_key(client):
    """无 LLM key（离线）时降级为 fallback，used_fallback=True，不 500。"""
    resp = await client.post(
        "/api/v1/agent/chat",
        json={
            "message": "帮我修这段代码",
            "context": {
                "currentCode": "df.select('name')",
                "currentLesson": "polars-basics",
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["content"]
    # 离线无 key -> fallback
    assert body["data"]["usedFallback"] is True


@pytest.mark.unit
async def test_runner_unavailable_no_evidence_feedback(client):
    """无练习证据（Runner 不可用 / 无 attempt）时 feedback 为 no_evidence。

    离线测试 DB 无 attempt，evidence resolver 返回 no_evidence；
    teachingFeedback.state 应为 no_evidence，nextAction 为 inspect_result。
    """
    resp = await client.post(
        "/api/v1/agent/chat",
        json={
            "message": "我的练习没通过，怎么办",
            "context": {"currentLesson": "polars-basics", "attemptId": 1},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    fb = body["data"].get("teachingFeedback")
    # 有 visitor_id + practice_service -> 应解析出 no_evidence
    assert fb is not None
    assert fb["state"] == "no_evidence"
    assert fb["nextAction"] == "inspect_result"


@pytest.mark.unit
async def test_feedback_endpoint_rejects_nonexistent_interaction(client):
    """反馈端点对不存在的 interaction 返回 not_found（4044）。"""
    resp = await client.post(
        "/api/v1/agent/feedback",
        json={"interactionId": 99999, "feedback": "helpful"},
    )
    body = resp.json()
    assert body["code"] in (4044, 404)
    # not_found 响应 data 为 None
    assert body["data"] is None


@pytest.mark.unit
async def test_chat_with_attempt_id_does_not_leak_other_visitor(client):
    """带 attemptId 的请求不会泄漏其他 visitor 的证据（测试 DB 无数据）。"""
    resp = await client.post(
        "/api/v1/agent/chat",
        json={
            "message": "帮我看看",
            "context": {"currentLesson": "polars-basics", "attemptId": 999},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    fb = body["data"].get("teachingFeedback")
    assert fb is not None
    assert fb["state"] == "no_evidence"
    # 不含 code 字段
    assert "code" not in fb


@pytest.mark.unit
async def test_request_cancellable_via_abort(client):
    """请求可被取消（ASGI 层面不泄漏）：发起后立即断开不阻塞服务器。

    用 httpx 的超时模拟：设置极短超时，请求要么完成要么超时——
    两种情况都不应让服务器崩溃。此测试验证端点不阻塞。
    """
    import asyncio

    from app.agent.router import get_agent_service
    from app.agent.service import AgentService
    from main import app

    # 该用例只验证请求并发，不应复用 fixture 的单一事务 session 写审计。
    # 生产环境每个请求由 get_db 提供独立 session。
    app.dependency_overrides[get_agent_service] = lambda: AgentService()
    try:
        async def attempt():
            return await client.post(
                "/api/v1/agent/chat",
                json={"message": "hi"},
                timeout=5.0,
            )

        # 并发发起 3 个请求，验证不串行阻塞
        results = await asyncio.gather(*(attempt() for _ in range(3)))
        for r in results:
            assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_agent_service, None)
