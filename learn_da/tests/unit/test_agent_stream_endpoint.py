"""流式对话端点（E3，SSE）的 HTTP 层测试。

只验证传输层契约：Content-Type、事件行格式、顺序、空消息 422。
生成内容本身在 ``test_agent_stream.py`` 里用脚本化 LLM 覆盖。
"""

import json

from app.agent.schemas import AgentChatData
from app.agent.service import AgentService


def parse_events(body: str) -> list[dict]:
    """把 ``data: {...}\\n\\n`` 的 SSE 文本拆成事件列表。"""
    events = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block.startswith("data: "):
            continue
        events.append(json.loads(block[len("data: "):]))
    return events


async def test_stream_endpoint_sets_sse_headers(client, monkeypatch):
    async def fake_stream(self, payload, visitor_id):
        yield {"type": "delta", "text": "你"}
        yield {"type": "delta", "text": "好"}
        yield {
            "type": "done",
            "data": AgentChatData(
                content="你好", model="test-model"
            ).model_dump(by_alias=True),
        }

    monkeypatch.setattr(AgentService, "chat_stream", fake_stream)

    resp = await client.post(
        "/api/v1/agent/chat/stream", json={"message": "你好"}
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    # 反向代理不能缓冲，否则增量会被攒成一整段
    assert resp.headers["x-accel-buffering"] == "no"


async def test_stream_endpoint_emits_one_data_line_per_event(client, monkeypatch):
    async def fake_stream(self, payload, visitor_id):
        yield {"type": "delta", "text": "先 "}
        yield {"type": "delta", "text": "group_by。"}
        yield {
            "type": "done",
            "data": AgentChatData(
                content="先 group_by。", model="test-model"
            ).model_dump(by_alias=True),
        }

    monkeypatch.setattr(AgentService, "chat_stream", fake_stream)

    resp = await client.post(
        "/api/v1/agent/chat/stream", json={"message": "怎么分组"}
    )
    events = parse_events(resp.text)

    assert [e["type"] for e in events] == ["delta", "delta", "done"]
    assert events[-1]["data"]["content"] == "先 group_by。"
    # 中文不能被转成 \uXXXX（前端直接显示）
    assert "先 " in resp.text


async def test_stream_endpoint_returns_422_for_empty_message(client):
    resp = await client.post("/api/v1/agent/chat/stream", json={"message": "   "})

    # 空消息在 SSE 建立之前就该被拒（HTTP 422 + 错误信封），否则前端会收到
    # 一个空流，还以为模型没说话。
    assert resp.status_code == 422
    assert resp.json()["msg"] == "message is required"


async def test_stream_endpoint_surfaces_service_crash_as_error_event(
    client, monkeypatch
):
    async def boom(self, payload, visitor_id):
        yield {"type": "delta", "text": "开头"}
        raise RuntimeError("模拟上游炸了")

    monkeypatch.setattr(AgentService, "chat_stream", boom)

    resp = await client.post(
        "/api/v1/agent/chat/stream", json={"message": "你好"}
    )
    events = parse_events(resp.text)

    # 已经吐了「开头」，异常只能变成 error 事件，不能 500（响应头已发出）
    assert resp.status_code == 200
    assert events[0]["type"] == "delta"
    assert events[-1] == {"type": "error", "reason": "upstream_error", "partial": True}
