import pytest

from app.agent.prompts import (
    build_chat_messages,
    build_context_block,
    build_explain_messages,
    build_fix_messages,
)
from app.agent.routing import AgentRoute, AgentRouter
from app.agent.results import parse_structured_result
from app.agent.tools import AGENT_TOOLS, get_agent_tool
from app.agent.knowledge import (
    EmbeddingConfig,
    KnowledgeChunk,
    KnowledgeRetriever,
    build_knowledge_block,
)
from app.agent.schemas import (
    AgentChatRequest,
    AgentContext,
    AgentRunVerification,
    ExplainCodeRequest,
    FixCodeRequest,
    FixCodeResponse,
)
from app.agent.service import AgentService
from app.sandbox.schemas import SandboxExecutionResult


class FakeSandboxService:
    def __init__(self, result):
        self.result = result
        self.executed_code = None

    def execute(self, code: str):
        self.executed_code = code
        return self.result


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


def test_fix_code_response_serializes_optional_verification():
    response = FixCodeResponse(
        fixed_code="print('ok')",
        explanation="修复完成",
        model="test-model",
        used_fallback=False,
        verification=AgentRunVerification(
            verified=True,
            status="success",
            stdout="ok\n",
            stderr="",
            execution_time=12,
            used_sandbox="fake",
        ),
    )

    body = response.model_dump(by_alias=True)

    assert body["fixedCode"] == "print('ok')"
    assert body["verification"]["verified"] is True
    assert body["verification"]["executionTime"] == 12
    assert body["verification"]["usedSandbox"] == "fake"


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


def test_tool_registry_contains_format_and_fallback_for_each_tool():
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
        assert "必须按以下格式回复" in tool.response_format
        assert tool.fallback_content


def test_parse_structured_result_extracts_sections_and_code_blocks():
    content = (
        "问题原因：\n"
        "变量 df 尚未定义。\n\n"
        "修复方式：\n"
        "先创建 DataFrame，再执行筛选。\n\n"
        "修复代码：\n"
        "```python\n"
        "print('ok')\n"
        "```\n\n"
        "验证建议：\n"
        "运行后应看到 ok。"
    )

    result = parse_structured_result("fix_code", content)

    assert result.kind == "fix_code"
    assert [section.title for section in result.sections] == [
        "问题原因",
        "修复方式",
        "修复代码",
        "验证建议",
    ]
    assert result.sections[0].content == "变量 df 尚未定义。"
    assert result.code_blocks[0].language == "python"
    assert result.code_blocks[0].code == "print('ok')"


def test_explain_prompt_requires_stable_sections():
    messages = build_explain_messages("print('ok')")
    content = messages[-1]["content"]

    assert "必须按以下格式回复" in content
    assert "结论：" in content
    assert "关键步骤：" in content
    assert "容易混淆：" in content
    assert "建议你试试：" in content


def test_fix_prompt_requires_stable_sections_and_code_block():
    messages = build_fix_messages("print(df)", "NameError")
    content = messages[-1]["content"]

    assert "必须按以下格式回复" in content
    assert "问题原因：" in content
    assert "修复方式：" in content
    assert "修复代码：" in content
    assert "```python" in content
    assert "验证建议：" in content


def test_chat_prompt_uses_exercise_format_instruction():
    messages = build_chat_messages(
        user_message="根据本课生成一个练习",
        history=[],
        context=None,
        max_turns=3,
        tool_name="generate_exercise",
    )
    content = messages[-1]["content"]

    assert "练习目标：" in content
    assert "任务：" in content
    assert "提示：" in content
    assert "完成后检查：" in content


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
    assert EmbeddingConfig(api_key=None, base_url="https://example.test", model="m").enabled is False
    assert EmbeddingConfig(api_key="key", base_url=None, model="m").enabled is False
    assert EmbeddingConfig(api_key="key", base_url="https://example.test", model=None).enabled is False
    assert EmbeddingConfig(api_key="key", base_url="https://example.test", model="m").enabled is True


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

    async def fake_ask_llm(messages):
        captured_messages.extend(messages)
        return "简短回答：\nLazyFrame 需要 collect()。\n\n下一步建议：\n运行一次 collect()。"

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.chat(AgentChatRequest(message="为什么 LazyFrame 不执行？"))

    assert result.route is not None
    assert result.route.tool_name == "general_chat"
    assert result.structured_result is not None
    assert result.structured_result.kind == "general_chat"
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

    async def fake_ask_llm(messages):
        return None

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.chat(AgentChatRequest(message="接下来怎么学"))

    assert router.messages == ["接下来怎么学"]
    assert result.tool_name == "suggest_next_step"
    assert result.route is not None
    assert result.route.confidence == 0.91
    assert result.structured_result is not None
    assert result.structured_result.sections[0].title == "当前状态"
    assert "当前状态：" in result.content


@pytest.mark.unit
async def test_fix_code_response_includes_structured_result(monkeypatch):
    service = AgentService(
        sandbox_service=FakeSandboxService(
            SandboxExecutionResult(
                status="success",
                stdout="ok\n",
                stderr="",
                execution_time=7,
                used_sandbox="fake",
            )
        ),
        knowledge_retriever=FakeKnowledgeRetriever([]),
    )

    async def fake_ask_llm(messages):
        return (
            "问题原因：\n变量未定义。\n\n"
            "修复方式：\n改为打印固定文本。\n\n"
            "修复代码：\n```python\nprint('ok')\n```\n\n"
            "验证建议：\n运行后看到 ok。"
        )

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.fix_code(
        FixCodeRequest(code="print(df)", errorMessage="NameError")
    )

    assert result.structured_result is not None
    assert result.structured_result.kind == "fix_code"
    assert result.structured_result.code_blocks[0].code == "print('ok')"


@pytest.mark.unit
async def test_explain_code_response_includes_structured_result(monkeypatch):
    service = AgentService(knowledge_retriever=FakeKnowledgeRetriever([]))

    async def fake_ask_llm(messages):
        return (
            "结论：\n这段代码打印 ok。\n\n"
            "关键步骤：\n1. 调用 print。\n\n"
            "容易混淆：\nprint 会直接输出。\n\n"
            "建议你试试：\n改成别的文本。"
        )

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.explain_code(ExplainCodeRequest(code="print('ok')"))

    assert result.structured_result is not None
    assert result.structured_result.kind == "explain_code"
    assert result.structured_result.sections[0].title == "结论"


@pytest.mark.unit
async def test_fix_code_verifies_llm_code_block(monkeypatch):
    service = AgentService(
        sandbox_service=FakeSandboxService(
            SandboxExecutionResult(
                status="success",
                stdout="ok\n",
                stderr="",
                execution_time=7,
                used_sandbox="fake",
            )
        )
    )

    async def fake_ask_llm(messages):
        return "原因：变量未定义。\n```python\nprint('ok')\n```"

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.fix_code(
        FixCodeRequest(
            code="print(df)",
            errorMessage="NameError: name 'df' is not defined",
        )
    )

    assert result.fixed_code == "print('ok')"
    assert result.used_fallback is False
    assert result.verification is not None
    assert result.verification.verified is True
    assert result.verification.status == "success"
    assert result.verification.stdout == "ok\n"
    assert service.sandbox_service.executed_code == "print('ok')"


@pytest.mark.unit
async def test_fix_code_marks_verification_false_when_sandbox_errors(monkeypatch):
    service = AgentService(
        sandbox_service=FakeSandboxService(
            SandboxExecutionResult(
                status="error",
                stdout="",
                stderr="NameError: still broken",
                execution_time=5,
                used_sandbox="fake",
            )
        )
    )

    async def fake_ask_llm(messages):
        return "修复建议：\n```python\nprint(df)\n```"

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.fix_code(
        FixCodeRequest(
            code="print(df)",
            errorMessage="NameError: name 'df' is not defined",
        )
    )

    assert result.used_fallback is False
    assert result.verification is not None
    assert result.verification.verified is False
    assert result.verification.status == "error"
    assert "still broken" in result.verification.stderr
