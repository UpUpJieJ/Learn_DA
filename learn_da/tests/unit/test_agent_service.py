import pytest

from app.agent.prompts import (
    SYSTEM_PROMPT,
    build_chat_messages,
    build_context_block,
)
from app.agent.routing import AgentRoute, AgentRouter
from app.agent.tools import AGENT_TOOLS, get_agent_tool
from app.agent.knowledge import (
    EmbeddingConfig,
    KnowledgeChunk,
    KnowledgeRetriever,
    build_knowledge_block,
)
from app.agent.schemas import AgentChatRequest, AgentContext
from app.agent.llm_client import LLMResult
from app.agent.service import AgentService


def llm_ok(content: str) -> LLMResult:
    return LLMResult(content=content, error_reason=None, latency_ms=0)


LLM_UNAVAILABLE = LLMResult(
    content=None, error_reason="no_api_key", latency_ms=0)


class FakeKnowledgeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.queries = []

    async def search(self, query: str, current_lesson: str | None = None, limit: int = 3):
        self.queries.append((query, current_lesson, limit))
        return self.chunks[:limit]


class FakeRouter:
    def __init__(self, route: AgentRoute):
        self.route = route
        self.messages = []

    def resolve(self, message: str) -> AgentRoute:
        self.messages.append(message)
        return self.route


def test_context_block_includes_lesson_output_and_error():
    context = AgentContext(
        currentLesson="polars-basics",
        lessonTitle="Polars 基础入门",
        lessonCategory="polars",
        lessonContent="这一课介绍 DataFrame、select 和 filter。",
        currentCode="df.select('name')",
        stdout="shape: (2, 1)",
        stderr="ColumnNotFoundError: age",
    )

    block = build_context_block(context)

    assert "当前课程：Polars 基础入门（polars-basics，polars）" in block
    assert "课程内容摘要：" in block
    assert "df.select('name')" in block
    assert "最近一次标准输出" in block
    assert "shape: (2, 1)" in block
    assert "最近一次执行错误" in block
    assert "ColumnNotFoundError" in block


def test_agent_resolves_exercise_and_next_step_tools():
    service = AgentService()

    assert service.resolve_tool_name("根据本课生成一个练习") == "generate_exercise"
    assert service.resolve_tool_name("我下一步应该学什么") == "suggest_next_step"


def test_router_returns_structured_decision_with_reason():
    route = AgentRouter().resolve("这段 Polars 代码报错了，帮我修复")

    assert route.tool_name == "fix_code"
    assert route.confidence >= 0.7
    assert route.reason
    assert route.matched_keyword in {"报错", "修复"}


def test_router_priority_prefers_fix_over_example_generation():
    route = AgentRouter().resolve("这个 polars 示例代码 error 了")

    assert route.tool_name == "fix_code"


def test_router_recognizes_general_python_example_requests():
    route = AgentRouter().resolve("给我一个 Python 函数示例")

    assert route.tool_name == "generate_example_code"
    assert route.reason == "用户希望获得课程相关示例或代码"


def test_tool_registry_contains_fallback_for_each_tool():
    expected_tools = {
        "generate_example_code",
        "generate_exercise",
        "fix_code",
        "explain_code",
        "suggest_next_step",
        "general_chat",
    }

    assert set(AGENT_TOOLS) == expected_tools
    for tool_name in expected_tools:
        tool = get_agent_tool(tool_name)
        assert tool.name == tool_name
        assert tool.fallback_content


def test_system_prompt_emphasizes_coach_role_and_no_direct_answer_bias():
    assert "通用学习教练" in SYSTEM_PROMPT
    assert "专门帮助有 Pandas 或 SQL 基础" not in SYSTEM_PROMPT
    assert "先解释思路" in SYSTEM_PROMPT
    assert "不要直接给最终答案" in SYSTEM_PROMPT
    assert "围绕当前课程和 Playground 上下文" in SYSTEM_PROMPT
    assert "不是代写工具" in SYSTEM_PROMPT
    assert "如果当前课程涉及 Polars、DuckDB、Pandas 或 SQL" in SYSTEM_PROMPT
    assert "1 到 3 个" in SYSTEM_PROMPT


def test_agent_fallbacks_are_general_learning_friendly():
    example_tool = get_agent_tool("generate_example_code")
    explain_tool = get_agent_tool("explain_code")
    next_tool = get_agent_tool("suggest_next_step")

    assert "DuckDB 在 Python 中查询内存数据" not in example_tool.fallback_content
    assert "Polars 或 DuckDB 的核心 API" not in explain_tool.fallback_content
    assert "数据分析代码" not in next_tool.fallback_content
    assert "当前课程" in explain_tool.fallback_content


@pytest.mark.unit
def test_chat_prompt_has_no_format_template():
    messages = build_chat_messages(
        user_message="根据本课生成一个练习",
        history=[],
        context=None,
        max_turns=3,
    )
    content = messages[-1]["content"]

    assert content == "根据本课生成一个练习"


def test_chat_prompt_for_exercise_preserves_hint_first_instruction():
    messages = build_chat_messages(
        user_message="根据本课生成一个练习",
        history=[],
        context=AgentContext(currentLesson="polars-basics"),
        max_turns=3,
    )
    system_messages = [message["content"]
                       for message in messages if message["role"] == "system"]

    assert any("不要直接给最终答案" in content for content in system_messages)


@pytest.mark.unit
async def test_keyword_retriever_returns_relevant_lesson_chunk():
    retriever = KnowledgeRetriever(
        lessons=[
            {
                "slug": "polars-lazy",
                "title": "Polars LazyFrame",
                "category": "polars",
                "content": "## Lazy 执行\nLazyFrame 需要 collect() 才会真正执行查询计划。",
            },
            {
                "slug": "duckdb-sql",
                "title": "DuckDB SQL",
                "category": "duckdb",
                "content": "## 分组聚合\nGROUP BY 用于按类别统计。",
            },
        ]
    )

    results = await retriever.search("为什么 LazyFrame 需要 collect", limit=1)

    assert results[0].lesson_slug == "polars-lazy"
    assert "collect()" in results[0].text


def test_knowledge_block_uses_stable_format():
    block = build_knowledge_block(
        [
            KnowledgeChunk(
                lesson_slug="polars-lazy",
                lesson_title="Polars LazyFrame",
                category="polars",
                heading="Lazy 执行",
                text="LazyFrame 需要 collect() 才会执行。",
                score=3.2,
            )
        ]
    )

    assert "相关知识点：" in block
    assert "Polars LazyFrame" in block
    assert "LazyFrame 需要 collect()" in block


def test_embedding_config_requires_key_url_and_model():
    assert EmbeddingConfig(
        api_key=None, base_url="https://example.test", model="m").enabled is False
    assert EmbeddingConfig(api_key="key", base_url=None,
                           model="m").enabled is False
    assert EmbeddingConfig(
        api_key="key", base_url="https://example.test", model=None).enabled is False
    assert EmbeddingConfig(
        api_key="key", base_url="https://example.test", model="m").enabled is True


@pytest.mark.unit
async def test_chat_injects_retrieved_knowledge(monkeypatch):
    retriever = FakeKnowledgeRetriever(
        [
            KnowledgeChunk(
                lesson_slug="polars-lazy",
                lesson_title="Polars LazyFrame",
                category="polars",
                heading="Lazy 执行",
                text="LazyFrame 需要 collect() 才会真正执行。",
                score=2.5,
            )
        ]
    )
    service = AgentService(knowledge_retriever=retriever)
    captured_messages = []

    async def fake_complete(messages):
        captured_messages.extend(messages)
        return llm_ok(
            "简短回答：\nLazyFrame 需要 collect()。\n\n下一步建议：\n运行一次 collect()。"
        )

    monkeypatch.setattr(service, "_complete", fake_complete)

    result = await service.chat(AgentChatRequest(message="为什么 LazyFrame 不执行？"))

    assert retriever.queries
    assert any("相关知识点：" in message["content"] for message in captured_messages)


@pytest.mark.unit
async def test_chat_uses_injected_router_decision(monkeypatch):
    router = FakeRouter(
        AgentRoute(
            tool_name="suggest_next_step",
            confidence=0.91,
            reason="用户询问下一步",
            matched_keyword="下一步",
        )
    )
    service = AgentService(
        knowledge_retriever=FakeKnowledgeRetriever([]),
        router=router,
    )

    async def fake_complete(messages):
        return LLM_UNAVAILABLE

    monkeypatch.setattr(service, "_complete", fake_complete)

    result = await service.chat(AgentChatRequest(message="接下来怎么学"))

    assert router.messages == ["接下来怎么学"]
    assert "当前状态：" in result.content


@pytest.mark.unit
async def test_chat_fallback_exposes_error_reason(monkeypatch):
    """Task 2.2: 降级时 fallback_reason 必须透出 LLM 错误分类。"""
    service = AgentService(knowledge_retriever=FakeKnowledgeRetriever([]))

    async def fake_complete(messages):
        return LLMResult(content=None, error_reason="rate_limited", latency_ms=3)

    monkeypatch.setattr(service, "_complete", fake_complete)

    result = await service.chat(AgentChatRequest(message="解释一下表达式"))

    assert result.used_fallback is True
    assert result.fallback_reason == "rate_limited"


@pytest.mark.unit
async def test_chat_success_has_no_fallback_reason(monkeypatch):
    service = AgentService(knowledge_retriever=FakeKnowledgeRetriever([]))

    async def fake_complete(messages):
        return llm_ok("这是回答")

    monkeypatch.setattr(service, "_complete", fake_complete)

    result = await service.chat(AgentChatRequest(message="解释一下表达式"))

    assert result.used_fallback is False
    assert result.fallback_reason is None
