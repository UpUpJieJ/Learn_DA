# Agent Context Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Agent backend understand recent chat history, current Playground code, and last error, then expose working `/agent/fix` and `/agent/explain` endpoints for the existing frontend panel.

**Architecture:** Keep the frontend unchanged for this iteration because `AgentPanel.vue` already sends `history` and `context`, and already calls `fixCode()` / `explainCode()`. Refactor backend Agent logic out of `router.py` into small files: schemas define API contracts, prompts build compact model instructions, service owns LLM calls and fallback behavior, router only wires FastAPI endpoints.

**Tech Stack:** FastAPI, Pydantic v2, OpenAI Python SDK `AsyncOpenAI`, pytest/httpx existing backend test setup.

---

## File Structure

- Create `learn_da/app/agent/schemas.py`: request/response models for chat, fix, explain, context, and message history.
- Create `learn_da/app/agent/prompts.py`: compact system prompts and prompt builders for chat, fix, and explain.
- Create `learn_da/app/agent/service.py`: `AgentService`, tool-name routing, LLM call wrapper, fallback responses.
- Modify `learn_da/app/agent/router.py`: replace inline logic with dependency-injected service and add `/fix` and `/explain`.
- Modify `learn_da/tests/test_health.py`: preserve current smoke test and add endpoint tests for context, fix, and explain fallback behavior.

## Task 1: Add Agent Schemas

**Files:**
- Create: `learn_da/app/agent/schemas.py`
- Test: `learn_da/tests/test_health.py`

- [ ] **Step 1: Write failing tests for accepted request shapes**

Add these tests to `learn_da/tests/test_health.py`:

```python
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
    assert body["data"]["content"]
    assert "model" in body["data"]
```

Run:

```bash
uv run pytest tests/test_health.py::test_agent_chat_accepts_history_and_context -q
```

Expected: fail because `history` and `context` are not modeled yet or are ignored by the current router.

- [ ] **Step 2: Create schema models**

Create `learn_da/app/agent/schemas.py`:

```python
from typing import Literal

from pydantic import BaseModel, Field

from app.utils.base_response import BaseResponseModel


MessageRole = Literal["user", "assistant", "system"]
ToolName = Literal["generate_example_code", "fix_code", "explain_code", "general_chat"]


class AgentChatMessage(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1, max_length=4000)


class AgentContext(BaseModel):
    current_code: str | None = Field(default=None, alias="currentCode", max_length=12000)
    last_error: str | None = Field(default=None, alias="lastError", max_length=4000)
    current_lesson: str | None = Field(default=None, alias="currentLesson", max_length=200)


class AgentChatPayload(BaseModel):
    message: str | None = Field(default=None, min_length=1, max_length=4000)


class AgentChatRequest(BaseModel):
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    payload: AgentChatPayload | None = None
    history: list[AgentChatMessage] = Field(default_factory=list, max_length=6)
    context: AgentContext | None = None


class AgentChatData(BaseResponseModel):
    tool_name: ToolName
    content: str
    model: str
    used_fallback: bool = False


class FixCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12000)
    error_message: str = Field(alias="errorMessage", min_length=1, max_length=4000)
    context: AgentContext | None = None


class FixCodeResponse(BaseResponseModel):
    fixed_code: str
    explanation: str
    model: str
    used_fallback: bool = False


class ExplainCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12000)
    context: AgentContext | None = None


class ExplainCodeResponse(BaseResponseModel):
    explanation: str
    model: str
    used_fallback: bool = False
```

- [ ] **Step 3: Run schema-targeted test**

Run:

```bash
uv run pytest tests/test_health.py::test_agent_chat_accepts_history_and_context -q
```

Expected: still fail until router imports and uses these schemas.

## Task 2: Add Prompt Builders

**Files:**
- Create: `learn_da/app/agent/prompts.py`
- Test: `learn_da/tests/test_health.py`

- [ ] **Step 1: Create prompt helpers**

Create `learn_da/app/agent/prompts.py`:

```python
from .schemas import AgentChatMessage, AgentContext


SYSTEM_PROMPT = (
    "你是一个 Polars 和 DuckDB 数据分析学习助手。"
    "回答要简洁、实用、面向初学者。"
    "如果问题超出 Polars、DuckDB、Python 数据分析、SQL 学习范围，"
    "请简短说明你主要能帮助这些主题。"
)


def compact_history(history: list[AgentChatMessage], max_turns: int) -> list[dict[str, str]]:
    recent = history[-max_turns * 2 :]
    return [{"role": item.role, "content": item.content} for item in recent]


def build_context_block(context: AgentContext | None) -> str:
    if not context:
        return ""

    parts: list[str] = []
    if context.current_lesson:
        parts.append(f"当前课程：{context.current_lesson}")
    if context.current_code:
        parts.append(f"当前 Playground 代码：\n```python\n{context.current_code[:4000]}\n```")
    if context.last_error:
        parts.append(f"最近一次执行错误：\n```text\n{context.last_error[:2000]}\n```")
    return "\n\n".join(parts)


def build_chat_messages(
    user_message: str,
    history: list[AgentChatMessage],
    context: AgentContext | None,
    max_turns: int,
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    context_block = build_context_block(context)
    if context_block:
        messages.append({"role": "system", "content": context_block})
    messages.extend(compact_history(history, max_turns=max_turns))
    messages.append({"role": "user", "content": user_message})
    return messages


def build_fix_messages(code: str, error_message: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "请修复这段 Python/Polars/DuckDB 学习代码。"
                "返回时先解释错误原因，再给出完整修复代码。\n\n"
                f"错误信息：\n```text\n{error_message[:3000]}\n```\n\n"
                f"代码：\n```python\n{code[:8000]}\n```"
            ),
        },
    ]


def build_explain_messages(code: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "请解释这段代码的作用。按执行流程、关键 API、可能输出三部分说明，"
                "保持简洁。\n\n"
                f"代码：\n```python\n{code[:8000]}\n```"
            ),
        },
    ]
```

- [ ] **Step 2: No standalone test yet**

Prompt helpers are covered through service/router tests in Task 3 and Task 4. Do not add brittle exact-string tests.

## Task 3: Add Agent Service

**Files:**
- Create: `learn_da/app/agent/service.py`
- Test: `learn_da/tests/test_health.py`

- [ ] **Step 1: Write failing tests for fallback fix/explain**

Add these tests to `learn_da/tests/test_health.py`:

```python
@pytest.mark.unit
async def test_agent_fix_returns_structured_fallback(client):
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


@pytest.mark.unit
async def test_agent_explain_returns_structured_fallback(client):
    resp = await client.post(
        "/api/v1/agent/explain",
        json={"code": "import polars as pl\nprint('ok')"},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["explanation"]
    assert body["data"]["usedFallback"] is True
```

Run:

```bash
uv run pytest tests/test_health.py::test_agent_fix_returns_structured_fallback tests/test_health.py::test_agent_explain_returns_structured_fallback -q
```

Expected: fail with 404 because endpoints do not exist.

- [ ] **Step 2: Create service implementation**

Create `learn_da/app/agent/service.py`:

```python
from openai import AsyncOpenAI

from config.settings import settings

from .prompts import build_chat_messages, build_explain_messages, build_fix_messages
from .schemas import (
    AgentChatData,
    AgentChatRequest,
    ExplainCodeRequest,
    ExplainCodeResponse,
    FixCodeRequest,
    FixCodeResponse,
    ToolName,
)


class AgentService:
    def __init__(self) -> None:
        self.model = settings.effective_llm_model

    def extract_user_message(self, payload: AgentChatRequest) -> str:
        if payload.message:
            return payload.message
        if payload.payload and payload.payload.message:
            return payload.payload.message
        return ""

    def resolve_tool_name(self, message: str) -> ToolName:
        text = message.lower()
        if any(keyword in text for keyword in ("报错", "错误", "error", "fix", "修复")):
            return "fix_code"
        if any(keyword in text for keyword in ("解释", "explain", "作用", "什么意思")):
            return "explain_code"
        if any(keyword in text for keyword in ("duckdb", "polars", "示例", "example", "代码")):
            return "generate_example_code"
        return "general_chat"

    async def chat(self, payload: AgentChatRequest) -> AgentChatData:
        user_message = self.extract_user_message(payload)
        tool_name = self.resolve_tool_name(user_message)
        messages = build_chat_messages(
            user_message=user_message,
            history=payload.history,
            context=payload.context,
            max_turns=settings.OPENAI_MAX_TURNS,
        )
        content = await self._ask_llm(messages)
        if content:
            return AgentChatData(
                tool_name=tool_name,
                content=content,
                model=self.model,
                used_fallback=False,
            )
        return AgentChatData(
            tool_name=tool_name,
            content=self._fallback_chat_content(tool_name),
            model=self.model,
            used_fallback=True,
        )

    async def fix_code(self, payload: FixCodeRequest) -> FixCodeResponse:
        content = await self._ask_llm(build_fix_messages(payload.code, payload.error_message))
        if content:
            return FixCodeResponse(
                fixed_code=self._extract_code_block(content) or payload.code,
                explanation=content,
                model=self.model,
                used_fallback=False,
            )
        return FixCodeResponse(
            fixed_code=payload.code,
            explanation=(
                "我暂时无法连接模型。根据错误信息看，代码引用了尚未定义的变量或对象。"
                "请先确认变量已经创建，再运行后续语句。"
            ),
            model=self.model,
            used_fallback=True,
        )

    async def explain_code(self, payload: ExplainCodeRequest) -> ExplainCodeResponse:
        content = await self._ask_llm(build_explain_messages(payload.code))
        if content:
            return ExplainCodeResponse(
                explanation=content,
                model=self.model,
                used_fallback=False,
            )
        return ExplainCodeResponse(
            explanation=(
                "我暂时无法连接模型。这段代码会按顺序执行 Python 语句；"
                "如果包含 Polars 或 DuckDB API，建议关注数据读取、转换、查询和输出这几个步骤。"
            ),
            model=self.model,
            used_fallback=True,
        )

    async def _ask_llm(self, messages: list[dict[str, str]]) -> str | None:
        api_key = settings.effective_llm_api_key
        if not api_key:
            return None

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.effective_llm_base_url,
        )
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
        )
        if not response.choices:
            return None
        message = response.choices[0].message
        return message.content if message else None

    def _fallback_chat_content(self, tool_name: ToolName) -> str:
        if tool_name == "generate_example_code":
            return (
                "下面是一个 DuckDB 示例：\n"
                "```sql\n"
                "SELECT category, COUNT(*) AS cnt\n"
                "FROM events\n"
                "GROUP BY category\n"
                "ORDER BY cnt DESC;\n"
                "```"
            )
        if tool_name == "fix_code":
            return "我已经看到你在排查代码错误。请把当前代码和完整报错一起发给我，我会按原因和修复代码两部分说明。"
        if tool_name == "explain_code":
            return "请把要解释的代码发给我，我会按执行流程和关键 API 简洁说明。"
        return "我已经收到你的问题。当前先使用降级回复，请稍后重试。"

    def _extract_code_block(self, content: str) -> str | None:
        marker = "```"
        start = content.find(marker)
        if start == -1:
            return None
        body_start = content.find("\n", start)
        if body_start == -1:
            return None
        end = content.find(marker, body_start + 1)
        if end == -1:
            return None
        return content[body_start + 1 : end].strip()
```

- [ ] **Step 3: Service tests still fail until router is wired**

Run:

```bash
uv run pytest tests/test_health.py::test_agent_fix_returns_structured_fallback tests/test_health.py::test_agent_explain_returns_structured_fallback -q
```

Expected: still fail with 404.

## Task 4: Wire Router Endpoints

**Files:**
- Modify: `learn_da/app/agent/router.py`
- Test: `learn_da/tests/test_health.py`

- [ ] **Step 1: Replace router internals**

Replace the contents of `learn_da/app/agent/router.py` with:

```python
from fastapi import APIRouter, Depends, Request

from app.utils.limiter import limiter
from app.utils.base_response import StdResp
from config.settings import settings

from .schemas import AgentChatData, AgentChatRequest, ExplainCodeRequest, ExplainCodeResponse, FixCodeRequest, FixCodeResponse
from .service import AgentService

router = APIRouter(prefix="/agent", tags=["agent"])


def get_agent_service() -> AgentService:
    return AgentService()


@router.post("/chat", response_model=StdResp[AgentChatData])
@limiter.limit(settings.RATE_LIMIT_AGENT_CHAT)
async def chat_with_agent(
    request: Request,
    payload: AgentChatRequest,
    service: AgentService = Depends(get_agent_service),
):
    user_message = service.extract_user_message(payload)
    if not user_message:
        return StdResp.error(msg="message is required", code=422).to_response()
    return StdResp.success(data=await service.chat(payload))


@router.post("/fix", response_model=StdResp[FixCodeResponse])
@limiter.limit(settings.RATE_LIMIT_AGENT_CHAT)
async def fix_code(
    request: Request,
    payload: FixCodeRequest,
    service: AgentService = Depends(get_agent_service),
):
    return StdResp.success(data=await service.fix_code(payload))


@router.post("/explain", response_model=StdResp[ExplainCodeResponse])
@limiter.limit(settings.RATE_LIMIT_AGENT_CHAT)
async def explain_code(
    request: Request,
    payload: ExplainCodeRequest,
    service: AgentService = Depends(get_agent_service),
):
    return StdResp.success(data=await service.explain_code(payload))
```

- [ ] **Step 2: Run endpoint tests**

Run:

```bash
uv run pytest tests/test_health.py::test_agent_chat_uses_learning_toolchain tests/test_health.py::test_agent_chat_accepts_history_and_context tests/test_health.py::test_agent_fix_returns_structured_fallback tests/test_health.py::test_agent_explain_returns_structured_fallback -q
```

Expected: all selected Agent tests pass.

## Task 5: Final Verification

**Files:**
- Test only.

- [ ] **Step 1: Run backend smoke tests**

Run:

```bash
uv run pytest tests/test_health.py -q
```

Expected: all tests in `tests/test_health.py` pass.

- [ ] **Step 2: Run full backend test suite**

Run:

```bash
uv run pytest -q
```

Expected: all backend tests pass. If unrelated tests fail, capture the failing test names and error messages before deciding whether they are in scope.

- [ ] **Step 3: Manual API checks**

Run backend locally if needed, then send:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agent/fix ^
  -H "Content-Type: application/json" ^
  -d "{\"code\":\"print(df)\",\"errorMessage\":\"NameError: name 'df' is not defined\"}"
```

Expected JSON data includes `fixedCode`, `explanation`, `model`, and `usedFallback`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agent/explain ^
  -H "Content-Type: application/json" ^
  -d "{\"code\":\"import polars as pl\nprint('ok')\"}"
```

Expected JSON data includes `explanation`, `model`, and `usedFallback`.

## Self-Review

- Spec coverage: This plan covers the agreed next iteration: `/agent/fix`, `/agent/explain`, chat history/context support, service extraction, and tests.
- Placeholder scan: No implementation step depends on unspecified functions or files.
- Type consistency: Frontend camelCase fields `currentCode`, `lastError`, `errorMessage`, `fixedCode`, and `usedFallback` are preserved through Pydantic aliases and `BaseResponseModel`.

