"""受限 Function Calling 编排测试（阶段 ④ Task 4.1）。

覆盖计划要求：
- mock LLM 依次返回 tool_call 与最终回答，断言工具被正确执行；
- 超过 AGENT_FC_MAX_TOOL_ROUNDS 轮后强制 tool_choice="none" 收敛；
- 未知工具名返回错误 tool 消息而不抛异常；
- 非法参数回传错误 tool 消息（一次机会），二次失败走 fallback。
"""

import json

from app.agent.fc_tools import FC_TOOLS, FCToolExecutor
from app.agent.knowledge import KnowledgeChunk
from app.agent.llm_client import LLMResult, LLMToolCall
from app.agent.schemas import (
    AgentChatData,
    AgentChatRequest,
)
from app.agent.service import AgentService
from config.settings import settings

VISITOR_ID = "visitor-fc-test"


def tool_call_result(name: str, arguments: str, call_id: str = "call-1") -> LLMResult:
    return LLMResult(
        content=None,
        error_reason=None,
        latency_ms=0,
        tool_calls=(LLMToolCall(id=call_id, name=name, arguments=arguments),),
    )


def final_result(content: str) -> LLMResult:
    return LLMResult(content=content, error_reason=None, latency_ms=0)


def error_result(reason: str) -> LLMResult:
    return LLMResult(content=None, error_reason=reason, latency_ms=0)


class ScriptedCompleter:
    """按脚本顺序返回 LLMResult，并记录每次调用的入参。"""

    def __init__(self, results: list[LLMResult]) -> None:
        self.results = list(results)
        self.calls: list[dict] = []

    async def __call__(self, messages, tools=None, tool_choice=None):
        self.calls.append(
            {
                "messages": [dict(m) for m in messages],
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        return self.results.pop(0)


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


class FakeLearnerState:
    async def get_completed_lessons(self, visitor_id):
        return ["polars-basics"]

    async def get_last_visited(self, visitor_id):
        return "polars-groupby"


class FakeRecommendation:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def get_recommendation(
        self, visitor_id, completed_lessons=None, current_lesson_slug=None
    ):
        self.calls.append({"visitor_id": visitor_id})

        class _Response:
            class _Primary:
                def model_dump(self, mode="json"):
                    return {
                        "type": "next_lesson",
                        "target_slug": "polars-groupby",
                        "target_title": "Polars 分组聚合",
                        "reason": "已完成前置课程",
                    }

            primary = _Primary()

        return _Response()


def build_service(completer, **kwargs) -> AgentService:
    service = AgentService(knowledge_retriever=FakeRetriever(), **kwargs)
    service._complete = completer
    return service


def chat_request(message: str = "polars 怎么分组聚合") -> AgentChatRequest:
    return AgentChatRequest(message=message)


# ---- 编排循环 ----


async def test_tool_call_then_final_answer():
    completer = ScriptedCompleter(
        [
            tool_call_result("search_knowledge",
                             json.dumps({"query": "分组聚合"})),
            final_result("group_by 之后接 agg 即可。"),
        ]
    )
    service = build_service(completer)

    data = await service.chat_with_tools(chat_request(), visitor_id=VISITOR_ID)

    assert data.used_fallback is False
    assert data.content == "group_by 之后接 agg 即可。"
    assert service.knowledge_retriever.queries == ["分组聚合"]
    assert len(completer.calls) == 2
    # 第二次调用的消息序列包含 assistant tool_calls 与 tool 结果回传
    roles = [m["role"] for m in completer.calls[1]["messages"]]
    assert "tool" in roles
    tool_message = next(
        m for m in completer.calls[1]["messages"] if m["role"] == "tool"
    )
    assert tool_message["tool_call_id"] == "call-1"
    assert "polars-basics" in tool_message["content"]


async def test_tools_passed_with_auto_choice_first_round():
    completer = ScriptedCompleter([final_result("直接回答")])
    service = build_service(completer)

    await service.chat_with_tools(chat_request(), visitor_id=VISITOR_ID)

    assert completer.calls[0]["tools"] == FC_TOOLS
    assert completer.calls[0]["tool_choice"] == "auto"


async def test_forced_answer_after_max_rounds():
    completer = ScriptedCompleter(
        [
            tool_call_result("search_knowledge",
                             json.dumps({"query": "a"}), "c1"),
            tool_call_result("search_knowledge",
                             json.dumps({"query": "b"}), "c2"),
            final_result("最终回答"),
        ]
    )
    service = build_service(completer)

    data = await service.chat_with_tools(chat_request(), visitor_id=VISITOR_ID)

    assert data.used_fallback is False
    assert data.content == "最终回答"
    # 2 轮工具 + 1 次最终回答 = 3 次 LLM 调用，第三次强制直接回答
    assert len(completer.calls) == settings.AGENT_FC_MAX_TOOL_ROUNDS + 1 == 3
    assert completer.calls[2]["tool_choice"] == "none"


async def test_tool_calls_after_force_falls_back():
    completer = ScriptedCompleter(
        [
            tool_call_result("search_knowledge",
                             json.dumps({"query": "a"}), "c1"),
            tool_call_result("search_knowledge",
                             json.dumps({"query": "b"}), "c2"),
            tool_call_result("search_knowledge",
                             json.dumps({"query": "c"}), "c3"),
        ]
    )
    service = build_service(completer)

    data = await service.chat_with_tools(chat_request(), visitor_id=VISITOR_ID)

    assert data.used_fallback is True
    assert data.fallback_reason == "upstream_error"
    assert len(completer.calls) == 3


async def test_unknown_tool_returns_error_tool_message():
    completer = ScriptedCompleter(
        [
            tool_call_result("delete_everything", "{}"),
            final_result("好的，换个方式回答。"),
        ]
    )
    service = build_service(completer)

    data = await service.chat_with_tools(chat_request(), visitor_id=VISITOR_ID)

    assert data.used_fallback is False
    tool_message = next(
        m for m in completer.calls[1]["messages"] if m["role"] == "tool"
    )
    assert "unknown_tool" in tool_message["content"]


async def test_invalid_params_gets_one_retry():
    completer = ScriptedCompleter(
        [
            tool_call_result("search_knowledge", "{}"),  # 缺 query，非法
            final_result("换个说法回答。"),
        ]
    )
    service = build_service(completer)

    data = await service.chat_with_tools(chat_request(), visitor_id=VISITOR_ID)

    assert data.used_fallback is False
    tool_message = next(
        m for m in completer.calls[1]["messages"] if m["role"] == "tool"
    )
    assert "invalid_params" in tool_message["content"]


async def test_second_invalid_params_falls_back():
    completer = ScriptedCompleter(
        [
            tool_call_result("search_knowledge", "{}", "c1"),
            tool_call_result("search_knowledge", "not json", "c2"),
        ]
    )
    service = build_service(completer)

    data = await service.chat_with_tools(chat_request(), visitor_id=VISITOR_ID)

    assert data.used_fallback is True
    assert data.fallback_reason == "invalid_tool_params"


async def test_llm_error_falls_back_with_reason():
    completer = ScriptedCompleter([error_result("rate_limited")])
    service = build_service(completer)

    data = await service.chat_with_tools(chat_request(), visitor_id=VISITOR_ID)

    assert data.used_fallback is True
    assert data.fallback_reason == "rate_limited"


async def test_recommendation_tool_maps_intent():
    completer = ScriptedCompleter(
        [
            tool_call_result("get_recommendation", "{}"),
            final_result("建议你学习 Polars 分组聚合。"),
        ]
    )
    recommendation = FakeRecommendation()
    service = build_service(completer, recommendation_service=recommendation)

    data = await service.chat_with_tools(chat_request(), visitor_id=VISITOR_ID)

    assert recommendation.calls[0]["visitor_id"] == VISITOR_ID


# ---- FCToolExecutor ----


async def test_executor_unknown_tool_not_raises():
    executor = FCToolExecutor(
        knowledge_retriever=FakeRetriever(), visitor_id=VISITOR_ID
    )
    execution = await executor.execute("drop_database", "{}")
    assert execution.ok is False
    assert "unknown_tool" in execution.output


async def test_executor_invalid_json_marks_invalid_params():
    executor = FCToolExecutor(
        knowledge_retriever=FakeRetriever(), visitor_id=VISITOR_ID
    )
    execution = await executor.execute("search_knowledge", "not-json")
    assert execution.ok is False
    assert execution.invalid_params is True


async def test_executor_progress_without_service_returns_error():
    executor = FCToolExecutor(
        knowledge_retriever=FakeRetriever(), visitor_id=VISITOR_ID
    )
    execution = await executor.execute("get_learner_progress", "{}")
    assert execution.ok is False
    assert "unavailable" in execution.output


async def test_executor_progress_returns_learner_state():
    executor = FCToolExecutor(
        knowledge_retriever=FakeRetriever(),
        visitor_id=VISITOR_ID,
        learner_state_service=FakeLearnerState(),
    )
    execution = await executor.execute("get_learner_progress", "{}")
    assert execution.ok is True
    payload = json.loads(execution.output)
    assert payload["completed_lessons"] == ["polars-basics"]
    assert payload["last_visited"] == "polars-groupby"


# ---- 配置与红线 ----


def test_fc_settings_defaults():
    # Step 2 评测通过（FC 90.2% ≥ 基线 43.9%）后默认开启
    assert settings.AGENT_FC_ENABLED is True
    assert settings.AGENT_FC_MAX_TOOL_ROUNDS == 2


def test_fc_tools_are_read_only():
    # 红线：只允许三个只读工具，不得出现执行/写入类工具
    names = {tool["function"]["name"] for tool in FC_TOOLS}
    assert names == {"search_knowledge",
                     "get_learner_progress", "get_recommendation"}


# ---- /chat 入口按 flag 分流（Task 4.2）----


async def test_chat_endpoint_uses_legacy_path_when_flag_disabled(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "AGENT_FC_ENABLED", False)
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    async def must_not_call(self, payload, visitor_id):
        raise AssertionError("flag 关闭时不得进入 FC 路径")

    monkeypatch.setattr(AgentService, "chat_with_tools", must_not_call)

    resp = await client.post(
        "/api/v1/agent/chat", json={"message": "解释一下 Polars 表达式"}
    )
    assert resp.status_code == 200
    body = resp.json()
    # 无 key 时旧路径确定性降级，行为与阶段 ③ 一致（响应 JSON 为驼峰键）
    assert body["data"]["usedFallback"] is True
    assert body["data"]["fallbackReason"] == "no_api_key"


async def test_chat_endpoint_uses_fc_path_when_flag_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_FC_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")

    captured: dict = {}

    async def fake_chat_with_tools(self, payload, visitor_id):
        captured["visitor_id"] = visitor_id
        return AgentChatData(
            tool_name="general_chat",
            content="FC 路径回答",
            model="test-model",
        )

    monkeypatch.setattr(AgentService, "chat_with_tools", fake_chat_with_tools)

    resp = await client.post("/api/v1/agent/chat", json={"message": "你好"})
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == "FC 路径回答"
    assert captured["visitor_id"]


async def test_chat_endpoint_flag_on_without_key_uses_legacy(client, monkeypatch):
    # 设计决策：无 key 时即使 flag 开启也走确定性降级旧路径
    monkeypatch.setattr(settings, "AGENT_FC_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    async def must_not_call(self, payload, visitor_id):
        raise AssertionError("无 key 时不得进入 FC 路径")

    monkeypatch.setattr(AgentService, "chat_with_tools", must_not_call)

    resp = await client.post("/api/v1/agent/chat", json={"message": "你好"})
    assert resp.status_code == 200
    assert resp.json()["data"]["usedFallback"] is True


# ---- 会话合约（Task 4.3）----


async def test_twenty_turn_history_contains_current_user_message_once():
    """history 只含已完成消息，当前消息仅由 prompt builder 追加一次。"""
    completed_history = []
    for turn in range(20):
        current_message = f"当前问题-{turn}"
        service = build_service(ScriptedCompleter([final_result("已回答")]))
        payload = AgentChatRequest(
            message=current_message,
            history=completed_history[-20:],
        )

        data = await service.chat_with_tools(payload, visitor_id=VISITOR_ID)

        assert data.used_fallback is False
        prompt_messages = service._complete.calls[0]["messages"]
        assert sum(
            message["role"] == "user" and message["content"] == current_message
            for message in prompt_messages
        ) == 1
        # FC prompt 只包含 system/user/assistant；内部 tool 消息不会进入下轮 history。
        assert all(message["role"] != "tool" for message in prompt_messages)
        completed_history.extend(
            [
                {"role": "user", "content": current_message},
                {"role": "assistant", "content": "已回答"},
            ]
        )
