# Agent 能力增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Learn DA Agent 更懂当前课程、当前代码和执行结果，并能给出可验证、可落地的学习建议与修复方案。

**Architecture:** 保持现有 FastAPI + 原生 OpenAI API + Vue AgentPanel 架构，不引入 LangChain。后端增强上下文装配、工具路由、知识检索和修复验证；前端增强快捷动作与结构化结果展示。每个能力都必须有后端单元测试或前端构建验证。

**Tech Stack:** FastAPI, Pydantic, OpenAI Python SDK, pytest, Vue 3, Pinia, TypeScript, Vite.

---

## 1. 当前状态

当前 Agent 已有这些基础能力：

- 后端接口：`POST /api/v1/agent/chat`、`/agent/fix`、`/agent/explain`
- 工具意图路由：`fix_code`、`explain_code`、`generate_exercise`、`suggest_next_step`、`generate_example_code`、`general_chat`
- 课程知识检索：优先 embedding，失败后关键词检索
- Playground 上下文：当前代码、stdout、stderr、课程标题、课程内容摘要
- 修复验证：`fix_code` 会尝试运行 LLM 返回的代码块
- 前端面板：聊天、解释代码、修复错误、生成练习、下一步建议

当前主要短板：

- 工具路由只靠关键词，复杂提问容易误判。
- 知识检索只返回片段，没有明确“引用来源”展示给前端。
- `chat` 的结构化结果有解析，但前端展示仍偏普通 Markdown 文本。
- `fix_code` 会验证代码，但失败时没有二次修正策略。
- Agent 没有独立“课程感知练习生成”和“下一步学习建议”的专门接口。

---

## 2. 迭代范围

本计划只做 Agent 能力增强，不做这些事情：

- 不增加账号系统。
- 不改成 LangChain。
- 不做真正流式 SSE。
- 不引入新数据库。
- 不重做 AgentPanel 视觉。

本轮建议分 4 个可独立提交的小阶段：

1. 上下文与引用增强
2. 工具路由与提示词增强
3. 修复验证闭环增强
4. 前端结构化展示与快捷动作增强

---

## 3. 文件结构

### 后端

- Modify: `learn_da/app/agent/schemas.py`
  - 增加 Agent 引用来源类型。
  - 为 chat/fix/explain 响应补充 `references`。

- Modify: `learn_da/app/agent/knowledge.py`
  - 让 `build_knowledge_block` 同时能产出给模型的文本和给前端展示的引用。
  - 保持关键词检索 fallback。

- Modify: `learn_da/app/agent/service.py`
  - 注入引用来源。
  - 增强 `fix_code`：当验证失败时返回明确验证失败说明。
  - 为后续专用接口预留内部方法，但不新增数据库。

- Modify: `learn_da/app/agent/prompts.py`
  - 强化“必须结合课程/代码/输出”的提示词。
  - 对练习、下一步建议、修复结果增加稳定格式要求。

- Modify: `learn_da/app/agent/routing.py`
  - 增加更细的规则和优先级，减少“示例代码”抢走“修复错误”的误判。

- Modify: `learn_da/app/agent/router.py`
  - 可选新增 `POST /agent/exercise` 和 `POST /agent/next-step`。
  - 如果前端继续走 `/agent/chat` 快捷动作，则本阶段不必新增路由。

- Modify/Test: `learn_da/tests/unit/test_agent_service.py`
  - 覆盖引用、路由、上下文注入、验证失败说明。

- Modify/Test: `learn_da/tests/test_health.py`
  - 覆盖接口 smoke test。

### 前端

- Modify: `learn_da_vue/src/types/api.ts`
  - 增加 `AgentReference` 类型。
  - 给 `AgentChatResponse`、`AgentStructuredResult` 对齐后端字段。

- Modify: `learn_da_vue/src/api/agent.ts`
  - 透传 references。
  - 快捷动作保持非流式兼容。

- Modify: `learn_da_vue/src/components/agent/AgentPanel.vue`
  - 展示结构化 sections、codeBlocks、references。
  - 保留当前纯文本兜底。

---

## 4. 成功标准

完成后应满足：

- Agent 回答能明确引用当前课程或相关课程片段。
- 对代码解释时，优先解释当前 Playground 代码，不泛泛讲概念。
- 对错误修复时，能返回：
  - 问题原因
  - 修复方式
  - 完整修复代码
  - 验证结果
  - 下一步建议
- 生成练习时，能结合当前课程，给出目标、任务、提示和检查方式。
- 前端能展示引用来源和结构化内容。
- `uv run pytest -q` 通过。
- `npm run build` 通过。

---

## 5. 分阶段实施任务

### Task 1: 增加 Agent 引用来源模型

**Files:**
- Modify: `learn_da/app/agent/schemas.py`
- Test: `learn_da/tests/unit/test_agent_service.py`

- [ ] **Step 1: Write failing schema serialization test**

Add this test to `learn_da/tests/unit/test_agent_service.py`:

```python
from app.agent.schemas import AgentReference, AgentChatData


def test_agent_chat_data_serializes_references():
    response = AgentChatData(
        tool_name="general_chat",
        content="结论：\nLazyFrame 需要 collect()。",
        references=[
            AgentReference(
                lesson_slug="polars-lazy-pipeline",
                lesson_title="Polars Lazy Pipeline",
                heading="Lazy 执行",
                category="polars",
                score=2.5,
            )
        ],
    )

    body = response.model_dump(by_alias=True)

    assert body["references"][0]["lessonSlug"] == "polars-lazy-pipeline"
    assert body["references"][0]["lessonTitle"] == "Polars Lazy Pipeline"
    assert body["references"][0]["heading"] == "Lazy 执行"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd learn_da
uv run pytest tests/unit/test_agent_service.py::test_agent_chat_data_serializes_references -q
```

Expected: FAIL because `AgentReference` does not exist.

- [ ] **Step 3: Add schema**

In `learn_da/app/agent/schemas.py`, add:

```python
class AgentReference(BaseResponseModel):
    lesson_slug: str
    lesson_title: str
    heading: str
    category: str
    score: float = 0.0
```

Then add this field to `AgentChatData`, `FixCodeResponse`, and `ExplainCodeResponse`:

```python
references: list[AgentReference] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_agent_chat_data_serializes_references -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add learn_da/app/agent/schemas.py learn_da/tests/unit/test_agent_service.py
git commit -m "feat(agent): add response references schema"
```

---

### Task 2: Return knowledge references from retrieval

**Files:**
- Modify: `learn_da/app/agent/knowledge.py`
- Modify: `learn_da/app/agent/service.py`
- Test: `learn_da/tests/unit/test_agent_service.py`

- [ ] **Step 1: Write failing reference extraction test**

Add:

```python
from app.agent.knowledge import build_knowledge_references


def test_build_knowledge_references_from_chunks():
    refs = build_knowledge_references(
        [
            KnowledgeChunk(
                lesson_slug="polars-lazy-pipeline",
                lesson_title="Polars Lazy Pipeline",
                category="polars",
                heading="Lazy 执行",
                text="LazyFrame 需要 collect()。",
                score=2.5,
            )
        ]
    )

    assert refs[0].lesson_slug == "polars-lazy-pipeline"
    assert refs[0].heading == "Lazy 执行"
    assert refs[0].score == 2.5
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_build_knowledge_references_from_chunks -q
```

Expected: FAIL because `build_knowledge_references` does not exist.

- [ ] **Step 3: Implement references builder**

In `learn_da/app/agent/knowledge.py`:

```python
from .schemas import AgentReference


def build_knowledge_references(chunks: list[KnowledgeChunk]) -> list[AgentReference]:
    return [
        AgentReference(
            lesson_slug=chunk.lesson_slug,
            lesson_title=chunk.lesson_title,
            heading=chunk.heading,
            category=chunk.category,
            score=chunk.score,
        )
        for chunk in chunks
    ]
```

- [ ] **Step 4: Modify AgentService to keep chunks**

In `learn_da/app/agent/service.py`, replace `_retrieve_knowledge` with a method that returns both block and references:

```python
async def _retrieve_knowledge_context(
    self,
    query: str,
    current_lesson: str | None,
) -> tuple[str, list[AgentReference]]:
    chunks = await self.knowledge_retriever.search(
        query=query,
        current_lesson=current_lesson,
        limit=3,
    )
    return build_knowledge_block(chunks), build_knowledge_references(chunks)
```

Update imports:

```python
from .knowledge import KnowledgeRetriever, build_knowledge_block, build_knowledge_references
from .schemas import AgentReference
```

Then update `chat`, `fix_code`, and `explain_code` to include `references=references` in their responses.

- [ ] **Step 5: Add chat response test**

Add:

```python
@pytest.mark.unit
async def test_chat_response_includes_knowledge_references(monkeypatch):
    retriever = FakeKnowledgeRetriever(
        [
            KnowledgeChunk(
                lesson_slug="polars-lazy-pipeline",
                lesson_title="Polars Lazy Pipeline",
                category="polars",
                heading="Lazy 执行",
                text="LazyFrame 需要 collect()。",
                score=2.5,
            )
        ]
    )
    service = AgentService(knowledge_retriever=retriever)

    async def fake_ask_llm(messages):
        return "结论：\nLazyFrame 需要 collect()。"

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.chat(AgentChatRequest(message="LazyFrame 为什么没执行？"))

    assert result.references
    assert result.references[0].lesson_slug == "polars-lazy-pipeline"
```

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_build_knowledge_references_from_chunks tests/unit/test_agent_service.py::test_chat_response_includes_knowledge_references -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add learn_da/app/agent/knowledge.py learn_da/app/agent/service.py learn_da/tests/unit/test_agent_service.py
git commit -m "feat(agent): include knowledge references"
```

---

### Task 3: Strengthen routing and prompts for course-aware answers

**Files:**
- Modify: `learn_da/app/agent/routing.py`
- Modify: `learn_da/app/agent/prompts.py`
- Test: `learn_da/tests/unit/test_agent_service.py`

- [ ] **Step 1: Add routing tests**

Add:

```python
def test_router_prefers_explain_for_what_does_this_code_do():
    route = AgentRouter().resolve("这段代码为什么要 collect，它在做什么")

    assert route.tool_name == "explain_code"


def test_router_prefers_next_step_for_learning_path_question():
    route = AgentRouter().resolve("我已经学完 group_by，接下来应该练什么")

    assert route.tool_name == "suggest_next_step"
```

- [ ] **Step 2: Run tests to verify failure if current behavior is wrong**

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_router_prefers_explain_for_what_does_this_code_do tests/unit/test_agent_service.py::test_router_prefers_next_step_for_learning_path_question -q
```

Expected: FAIL if router chooses `generate_example_code` too early.

- [ ] **Step 3: Adjust routing rules**

In `learn_da/app/agent/routing.py`, update rules:

```python
rules: tuple[tuple[ToolName, tuple[str, ...], float, str], ...] = (
    (
        "fix_code",
        ("报错", "错误", "error", "traceback", "exception", "fix", "修复", "不能运行"),
        0.9,
        "用户正在排查代码错误或请求修复",
    ),
    (
        "explain_code",
        ("解释", "explain", "作用", "什么意思", "为什么", "做什么", "这段代码"),
        0.84,
        "用户希望理解代码、输出或概念",
    ),
    (
        "suggest_next_step",
        ("下一步", "next step", "继续学", "学什么", "接下来", "练什么", "路线"),
        0.83,
        "用户希望获得学习路径建议",
    ),
    (
        "generate_exercise",
        ("练习", "exercise", "题目", "出题", "测验", "小任务"),
        0.82,
        "用户希望生成练习任务",
    ),
    (
        "generate_example_code",
        ("示例", "example", "代码样例", "写一段", "给我代码"),
        0.74,
        "用户希望获得数据分析示例或代码",
    ),
)
```

- [ ] **Step 4: Strengthen prompt**

In `learn_da/app/agent/prompts.py`, update `SYSTEM_PROMPT`:

```python
SYSTEM_PROMPT = (
    "你是 Learn DA 的数据分析学习助手，专注 Polars、DuckDB、Python 数据分析和 SQL 学习。"
    "回答必须简洁、可执行、贴合当前课程和 Playground 上下文。"
    "如果提供了课程内容、当前代码、标准输出或错误信息，必须优先使用这些上下文。"
    "如果引用课程知识，请明确指出相关课程或小节。"
    "如果信息不足，先给最可能原因和一个可验证的下一步，不要编造不存在的 API。"
    "除非用户明确要求，不要输出长篇背景知识。"
)
```

- [ ] **Step 5: Run routing and prompt tests**

Run:

```bash
uv run pytest tests/unit/test_agent_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add learn_da/app/agent/routing.py learn_da/app/agent/prompts.py learn_da/tests/unit/test_agent_service.py
git commit -m "feat(agent): improve routing and prompts"
```

---

### Task 4: Make fix verification failures explicit

**Files:**
- Modify: `learn_da/app/agent/service.py`
- Test: `learn_da/tests/unit/test_agent_service.py`

- [ ] **Step 1: Add failing test**

Add:

```python
@pytest.mark.unit
async def test_fix_code_mentions_failed_verification(monkeypatch):
    service = AgentService(
        sandbox_service=FakeSandboxService(
            SandboxExecutionResult(
                status="error",
                stdout="",
                stderr="NameError: still broken",
                execution_time=5,
                used_sandbox="fake",
            )
        ),
        knowledge_retriever=FakeKnowledgeRetriever([]),
    )

    async def fake_ask_llm(messages):
        return (
            "问题原因：\n变量未定义。\n\n"
            "修复方式：\n尝试打印 df。\n\n"
            "修复代码：\n```python\nprint(df)\n```\n\n"
            "验证建议：\n运行代码。"
        )

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.fix_code(
        FixCodeRequest(code="print(df)", errorMessage="NameError")
    )

    assert result.verification is not None
    assert result.verification.verified is False
    assert "自动验证未通过" in result.explanation
    assert "NameError: still broken" in result.explanation
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_fix_code_mentions_failed_verification -q
```

Expected: FAIL because explanation does not mention failed verification.

- [ ] **Step 3: Add verification note**

In `AgentService.fix_code`, after `verification = self._verify_fixed_code(fixed_code)`, append a note when verification fails:

```python
verification = self._verify_fixed_code(fixed_code)
explanation = content
if not verification.verified:
    explanation = (
        f"{content}\n\n"
        "自动验证未通过：\n"
        f"状态：{verification.status}\n"
        f"错误输出：\n```text\n{verification.stderr[:2000]}\n```"
    )
return FixCodeResponse(
    fixed_code=fixed_code,
    explanation=explanation,
    model=self.model,
    used_fallback=False,
    verification=verification,
    references=references,
    structured_result=parse_structured_result("fix_code", explanation),
)
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/unit/test_agent_service.py::test_fix_code_mentions_failed_verification -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add learn_da/app/agent/service.py learn_da/tests/unit/test_agent_service.py
git commit -m "feat(agent): explain failed fix verification"
```

---

### Task 5: Surface structured results and references in frontend

**Files:**
- Modify: `learn_da_vue/src/types/api.ts`
- Modify: `learn_da_vue/src/api/agent.ts`
- Modify: `learn_da_vue/src/components/agent/AgentPanel.vue`

- [ ] **Step 1: Add frontend types**

In `learn_da_vue/src/types/api.ts`, add:

```ts
export interface AgentReference {
    lessonSlug: string;
    lessonTitle: string;
    heading: string;
    category: string;
    score: number;
}
```

Update:

```ts
export interface AgentChatResponse {
    reply: string;
    suggestedCode?: string;
    references?: AgentReference[];
    toolName?: AgentToolName;
    model?: string;
    usedFallback?: boolean;
    route?: AgentRouteInfo | null;
    structuredResult?: AgentStructuredResult | null;
}
```

- [ ] **Step 2: Pass references through API**

In `learn_da_vue/src/api/agent.ts`, update `AgentChatBackendData`:

```ts
references?: AgentReference[]
```

Update return:

```ts
return {
  reply,
  references: data.references ?? [],
  toolName: data.toolName,
  model: data.model,
  usedFallback: data.usedFallback,
  route: data.route,
  structuredResult: data.structuredResult,
}
```

- [ ] **Step 3: Store metadata on messages**

If `ChatMessage` does not already support metadata, extend it in `types/api.ts`:

```ts
structuredResult?: AgentStructuredResult | null;
references?: AgentReference[];
```

In `AgentPanel.vue`, inside `onDone`, assign:

```ts
msg.structuredResult = result.structuredResult ?? null
msg.references = result.references ?? []
```

This requires `streamChatMessage` to return `result` from the awaited call:

```ts
const result = await streamChatMessage({ ... })
```

- [ ] **Step 4: Render references**

In `AgentPanel.vue`, below assistant content, render:

```vue
<div
  v-if="msg.references?.length"
  class="mt-3 rounded-lg border border-white/10 bg-white/[0.03] p-2"
>
  <p class="mb-1 text-[11px] font-semibold text-slate-500">参考课程</p>
  <div class="space-y-1">
    <button
      v-for="ref in msg.references"
      :key="`${ref.lessonSlug}-${ref.heading}`"
      class="block w-full truncate rounded px-2 py-1 text-left text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200"
      @click="$router.push(`/learn/${ref.lessonSlug}`)"
    >
      {{ ref.lessonTitle }} / {{ ref.heading }}
    </button>
  </div>
</div>
```

If `$router` is not available in script setup, import `useRouter`:

```ts
import { useRouter } from "vue-router";
const router = useRouter();
```

And use `@click="router.push(`/learn/${ref.lessonSlug}`)"`.

- [ ] **Step 5: Build frontend**

Run:

```bash
cd learn_da_vue
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add learn_da_vue/src/types/api.ts learn_da_vue/src/api/agent.ts learn_da_vue/src/components/agent/AgentPanel.vue
git commit -m "feat(agent): show structured references"
```

---

### Task 6: Add API smoke tests for references

**Files:**
- Modify: `learn_da/tests/test_health.py`

- [ ] **Step 1: Add smoke test**

Add:

```python
@pytest.mark.unit
async def test_agent_chat_returns_references_field(client):
    resp = await client.post(
        "/api/v1/agent/chat",
        json={"message": "LazyFrame 为什么需要 collect？"},
    )
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert "references" in body["data"]
    assert isinstance(body["data"]["references"], list)
```

- [ ] **Step 2: Run smoke test**

Run:

```bash
cd learn_da
uv run pytest tests/test_health.py::test_agent_chat_returns_references_field -q
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run:

```bash
uv run pytest -q
cd ../learn_da_vue
npm run build
```

Expected:

- Backend: all tests pass.
- Frontend: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add learn_da/tests/test_health.py
git commit -m "test(agent): cover references in chat api"
```

---

## 6. Release Notes Draft

After implementation, update `README.md` Agent section with:

```markdown
### AI Agent 助手

- 结合当前课程、Playground 代码、标准输出和错误信息回答问题。
- 支持代码解释、错误修复、练习生成、下一步学习建议和示例代码生成。
- 回答会尽量附带相关课程引用，便于回到课程继续学习。
- 修复代码时会尝试运行修复结果，并返回验证状态。
```

---

## 7. Verification Checklist

Before considering the Agent enhancement complete:

- [ ] `uv run pytest -q` passes.
- [ ] `npm run build` passes.
- [ ] `/api/v1/agent/chat` returns `references`.
- [ ] `/api/v1/agent/fix` returns verification status.
- [ ] AgentPanel renders normal text when no structured result exists.
- [ ] AgentPanel renders references when backend returns them.
- [ ] Existing fallback mode still works when no LLM key is configured.
- [ ] No new database dependency is introduced.

---

## 8. Recommended Execution Order

1. Task 1: schemas
2. Task 2: knowledge references
3. Task 3: routing and prompts
4. Task 4: fix verification feedback
5. Task 5: frontend rendering
6. Task 6: smoke tests and docs

This order keeps the backend contract stable before the frontend starts relying on it.
