"""流式对话（E3，SSE）编排测试。

覆盖要点：
- 文本增量按顺序下发，且 done 事件里带完整 AgentChatData；
- 工具轮先发 tool 事件、工具执行后再续一轮流；
- 已吐字之后中断不重试、不当成功，发 error(partial=true) + done；
- 一轮字都没吐的失败走确定性降级文案，不假装成功；
- 同 request_id 重放不重复调用模型。
"""

import json
from contextlib import asynccontextmanager

from app.agent.fc_tools import FC_TOOLS
from app.agent.knowledge import KnowledgeChunk
from app.agent.llm_client import LLMStreamEvent, LLMToolCall
from app.agent.schemas import AgentChatRequest
from app.agent.service import AgentService, FALLBACK_UNAVAILABLE_CONTENT

VISITOR_ID = "visitor-stream-test"


class FakeRetriever:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.last_retrieval_mode = "keyword"

    async def search(self, query, current_lesson=None, limit=3):
        self.queries.append(query)
        return [
            KnowledgeChunk(
                lesson_slug="polars-basics",
                lesson_title="Polars 基础",
                category="polars",
                heading="概览",
                text="Polars 是高性能 DataFrame 库",
                score=1.0,
            )
        ]


class ScriptedStreamLLM:
    """按脚本顺序返回若干轮的流式事件，并记录每次调用的入参。"""

    def __init__(self, rounds: list[list[LLMStreamEvent]]) -> None:
        self.rounds = list(rounds)
        self.calls: list[dict] = []

    async def stream(self, messages, tools=None, tool_choice=None):
        self.calls.append(
            {
                "messages": [dict(m) for m in messages],
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        for event in self.rounds.pop(0):
            yield event

    async def complete(self, messages, tools=None, tool_choice=None):
        raise AssertionError("流式路径不应调用 complete")


def build_service(llm) -> AgentService:
    service = AgentService(knowledge_retriever=FakeRetriever())

    @asynccontextmanager
    async def fake_llm():
        yield llm

    service._llm = fake_llm
    return service


def text_round(*chunks: str) -> list[LLMStreamEvent]:
    events = [LLMStreamEvent(delta=chunk) for chunk in chunks]
    events.append(
        LLMStreamEvent(
            done=True,
            latency_ms=120,
            prompt_tokens=10,
            completion_tokens=5,
        )
    )
    return events


def tool_round(name: str, arguments: dict, call_id: str = "call-1"):
    return [
        LLMStreamEvent(
            done=True,
            latency_ms=80,
            tool_calls=(
                LLMToolCall(id=call_id, name=name, arguments=json.dumps(arguments)),
            ),
        )
    ]


def error_round(reason: str, *, interrupted: bool = False):
    return [
        LLMStreamEvent(
            done=True, error_reason=reason, latency_ms=30, interrupted=interrupted
        )
    ]


async def collect(service: AgentService, message: str = "polars 怎么分组聚合"):
    events = []
    async for event in service.chat_stream(
        AgentChatRequest(message=message), visitor_id=VISITOR_ID
    ):
        events.append(event)
    return events


def deltas(events: list[dict]) -> str:
    return "".join(e["text"] for e in events if e["type"] == "delta")


def done_event(events: list[dict]) -> dict:
    return next(e for e in events if e["type"] == "done")["data"]


# ---- 纯文本流 ----


async def test_text_deltas_stream_in_order_and_done_carries_full_data():
    llm = ScriptedStreamLLM([text_round("先 ", "group_by ", "再 agg。")])
    service = build_service(llm)

    events = await collect(service)

    assert deltas(events) == "先 group_by 再 agg。"
    assert [e["type"] for e in events] == ["delta", "delta", "delta", "done"]
    data = done_event(events)
    assert data["content"] == "先 group_by 再 agg。"
    assert data["usedFallback"] is False
    assert data["fallbackReason"] is None
    # 第一轮用 auto 让模型可以决定调工具
    assert llm.calls[0]["tools"] == FC_TOOLS
    assert llm.calls[0]["tool_choice"] == "auto"


async def test_delta_events_arrive_before_the_done_event():
    """流式的意义就是先看到字：done 必须是最后一条。"""
    llm = ScriptedStreamLLM([text_round("a", "b", "c")])
    service = build_service(llm)

    events = await collect(service)

    assert events[-1]["type"] == "done"
    assert all(e["type"] == "delta" for e in events[:-1])


# ---- 工具轮 ----


async def test_tool_round_emits_tool_event_then_continues_streaming():
    llm = ScriptedStreamLLM(
        [
            tool_round("search_knowledge", {"query": "分组聚合"}),
            text_round("group_by 之后接 agg。"),
        ]
    )
    service = build_service(llm)

    events = await collect(service)

    tool_events = [e for e in events if e["type"] == "tool"]
    assert len(tool_events) == 1
    assert tool_events[0]["names"] == ["search_knowledge"]
    assert deltas(events) == "group_by 之后接 agg。"
    assert done_event(events)["usedFallback"] is False
    # 工具真的被执行了
    assert service.knowledge_retriever.queries == ["分组聚合"]
    # 第二轮消息里带 tool 结果
    roles = [m["role"] for m in llm.calls[1]["messages"]]
    assert "tool" in roles


async def test_tool_event_comes_before_the_final_text():
    llm = ScriptedStreamLLM(
        [
            tool_round("get_task_summary", {"lesson_slug": "polars-groupby"}),
            text_round("你 t1 还没过。"),
        ]
    )
    service = build_service(llm)

    events = await collect(service)

    types = [e["type"] for e in events]
    assert types.index("tool") < types.index("delta")


async def test_forced_answer_round_disables_tools():
    llm = ScriptedStreamLLM(
        [
            tool_round("search_knowledge", {"query": "a"}, "c1"),
            tool_round("search_knowledge", {"query": "b"}, "c2"),
            text_round("最终回答"),
        ]
    )
    service = build_service(llm)

    events = await collect(service)

    assert deltas(events) == "最终回答"
    assert llm.calls[-1]["tool_choice"] == "none"


# ---- 失败与中断 ----


async def test_failure_before_any_text_uses_deterministic_fallback():
    llm = ScriptedStreamLLM([error_round("upstream_error")])
    service = build_service(llm)

    events = await collect(service)

    # 一个字都没吐过：可以把降级文案当成回答下发
    assert deltas(events) == FALLBACK_UNAVAILABLE_CONTENT
    data = done_event(events)
    assert data["usedFallback"] is True
    assert data["fallbackReason"] == "upstream_error"
    # 没有 partial 的 error 事件（内容完整，只是不可用）
    assert not [e for e in events if e["type"] == "error"]


async def test_interruption_after_text_marks_partial_and_does_not_fake_success():
    llm = ScriptedStreamLLM(
        [
            [
                LLMStreamEvent(delta="我先看"),
                LLMStreamEvent(delta="一下你的代码"),
                LLMStreamEvent(
                    done=True,
                    error_reason="stream_interrupted",
                    latency_ms=5000,
                    interrupted=True,
                ),
            ]
        ]
    )
    service = build_service(llm)

    events = await collect(service)

    assert deltas(events) == "我先看一下你的代码"
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["partial"] is True
    data = done_event(events)
    # 内容保留但明确标为降级，不假装成功
    assert data["usedFallback"] is True
    assert data["fallbackReason"] == "stream_interrupted"
    assert data["content"] == "我先看一下你的代码"


async def test_interrupted_stream_is_not_retried():
    """已吐字后中断不能重试，否则学习者会看到重复的开头。"""
    llm = ScriptedStreamLLM(
        [
            [
                LLMStreamEvent(delta="半句"),
                LLMStreamEvent(
                    done=True, error_reason="stream_interrupted", interrupted=True
                ),
            ]
        ]
    )
    service = build_service(llm)

    events = await collect(service)

    assert len(llm.calls) == 1
    assert deltas(events) == "半句"


async def test_forced_answer_without_content_falls_back():
    llm = ScriptedStreamLLM(
        [
            tool_round("search_knowledge", {"query": "a"}, "c1"),
            tool_round("search_knowledge", {"query": "b"}, "c2"),
            [LLMStreamEvent(done=True, latency_ms=10)],
        ]
    )
    service = build_service(llm)

    events = await collect(service)

    assert deltas(events) == FALLBACK_UNAVAILABLE_CONTENT
    assert done_event(events)["usedFallback"] is True


# ---- 幂等 ----


async def test_duplicate_request_id_does_not_call_the_model_again():
    llm = ScriptedStreamLLM([text_round("不该被调用")])
    service = build_service(llm)

    class _Reservation:
        async def _reserve_interaction(self, *, visitor_id, evidence):
            return 42, False

    service._reserve_interaction = _Reservation()._reserve_interaction

    events = await collect(service)

    assert llm.calls == []
    data = done_event(events)
    assert data["fallbackReason"] == "duplicate_request"
    assert data["interactionId"] == 42
