# Agent 重构与受限 Function Calling 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**制定日期：** 2026-07-28
**依据：** [`iteration-roadmap-2026-07-14.md`](../../iteration-roadmap-2026-07-14.md) 阶段 3、[`agent-system-review-2026-07-14.md`](../../agent-system-review-2026-07-14.md) R-04/R-05/R-07/R-08/R-09

**Goal:** 把 Agent 模块从"关键词路由 + 格式模板 + 正则解析"的单轮文本助手，重构为"共享生命周期 + 可观测 LLM 调用层 + 受限单步 Function Calling"的教学助手。FC 不是独立项目，而是本次重构的第 ④ 阶段；①②③ 是 FC 的硬前置，且即使不上 FC 也不浪费。

**Architecture:**
- `RecommendationService` 仍是推荐排序唯一来源，模型只解释不排序（Phase 3 结论保留）。
- 不给模型任何代码执行工具；沙箱执行仍走 Playground 用户主动触发（阶段 0 安全边界保留）。
- 无 API key 时的确定性降级路径全程保留：关键词路由降级为 fallback 选择器。
- FC 采用 feature flag 灰度，评测集对比通过后才默认开启。

**Tech Stack:** FastAPI lifespan、Pydantic v2、AsyncOpenAI（chat.completions + tools）、SQLAlchemy/Alembic（embedding 缓存表）、pytest。

---

## 总体阶段与依赖

```
① 生命周期收口（零合约变更）
        │
② LLM 调用层抽象（超时/重试/错误分类/指标）
        │
③ 评测集基线（关键词路由准确率、检索 hit@3）
        │
④ 受限 FC 改造（单入口 + 只读工具 + 步数上限 + 会话合约收口）
```

每个阶段独立可验收、可合并；④ 未通过评测对比时，flag 关闭即回到 ③ 结束时的形态。

## Scope

本计划做：
- lifespan 共享 `KnowledgeRetriever` / LLM client / embedding 索引，embedding 按内容哈希持久化。
- LLM 调用层：总超时、有限重试、错误分类、`fallback_reason`、route/latency/token 日志。
- 30-50 条意图路由 + 检索离线评测集与基线报告。
- 受限单步 FC：单 `/chat` 入口、3 个只读工具、最多 2 轮工具调用、结构化最终回答。
- 会话合约收口（history 不含当前消息、20 轮契约测试）与前端取消传播修复。
- 删除 `results.py` 正则解析与 `tools.py` 回复格式模板（fallback 文案保留）。

本计划不做：
- 多步 ReAct / 自主规划 / 给模型沙箱执行工具。
- LLM 参与推荐排序。
- SSE 逐 token 流式（留待有真实体验需求时单独立项）。
- attempt 上下文工具（依赖阶段 2 的尝试模型，本计划只留好接口位）。

---

## 阶段 ①：生命周期收口

**目标：** 消除每请求重建 `KnowledgeRetriever`/`AsyncOpenAI` 与全量重嵌 embedding（R-04），为 FC 的多次调用打成本地基。零 API 合约变更。

### Task 1.1: KnowledgeRetriever 提升为 lifespan 单例

**Files:**
- Modify: `learn_da/main.py`（lifespan 中创建 `app.state.knowledge_retriever`，参照 `runner_client` 先例）
- Modify: `learn_da/app/agent/router.py`（`get_agent_service` 从 `request.app.state` 注入 retriever）
- Modify: `learn_da/app/agent/service.py`（`AgentService` 不再默认自建 retriever，构造参数保持可注入以便测试）
- Test: `learn_da/tests/unit/test_agent_lifecycle.py`（新建）

- [x] **Step 1:** 写失败测试：两次请求 `/agent/chat` 使用同一个 retriever 实例（通过 app.state 断言 id 相同）。
- [x] **Step 2:** lifespan 中构建 retriever（`load_all_lessons()` 只在启动时执行一次），dependency 改为从 `request.app.state.knowledge_retriever` 读取。
- [x] **Step 3:** 全量回归：`.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp`。

**验收标准：**
- 课程 Markdown 只在启动时加载一次；单测中可继续用自建 retriever 注入。
- 现有 agent 相关测试全部通过，无 API 行为变化。

### Task 1.2: embedding 按内容哈希持久化

**Files:**
- Create: `learn_da/app/agent/embedding_cache.py`（缓存读写）
- Create: Alembic migration（新表 `agent_embeddings`：`chunk_hash` PK、`model`、`dimension`、`vector`(JSON)、`created_at`）
- Modify: `learn_da/app/agent/knowledge.py`（`_embedding_search` 前先查缓存，miss 的 chunk 才调 embedding API，结果写回）
- Test: `learn_da/tests/unit/test_embedding_cache.py`（新建）

- [x] **Step 1:** 写失败测试：相同 chunk 内容第二次检索时 embedding client 的 `embed_texts` 不被调用（mock 计数）；内容变更后仅重嵌变更的 chunk。
- [x] **Step 2:** 实现 `chunk_hash = sha256(model + chunk_text_for_embedding)`；缓存键含模型名，换模型自动失效。
- [x] **Step 3:** 采用惰性构建：首次命中 embedding 检索时批量补齐缺失向量并持久化，不阻塞应用启动。
- [x] **Step 4:** 迁移脚本 `alembic upgrade head` / `downgrade -1` 双向验证。

**验收标准：**
- 应用重启后，课程内容未变时不发生任何 chunk 重嵌（只嵌 query）。
- 修改单节课程内容后，只有该课程的 chunk 被重新嵌入。
- 满足 roadmap 阶段 3 验收项"相同课程版本的 embedding 只构建一次"。

### Task 1.3: 共享 LLM/embedding client 并显式关闭

**Files:**
- Modify: `learn_da/main.py`（lifespan 创建并在 shutdown `close()`）
- Modify: `learn_da/app/agent/knowledge.py`、`learn_da/app/agent/service.py`（复用注入的 client，删除方法内 `AsyncOpenAI(...)` 就地构建）

- [x] **Step 1:** lifespan 中按配置创建 `app.state.agent_llm_client`（AsyncOpenAI），无 key 时为 `None`；router 依赖注入，`_ask_llm` 未注入时自建自关。
- [x] **Step 2:** shutdown 时 `await client.close()`。
- [x] **Step 3:** 全量回归测试（160 passed）。

**验收标准：** 单个进程生命周期内 `AsyncOpenAI` 实例数固定，不随请求增长；关闭时无未释放连接警告。

---

## 阶段 ②：LLM 调用层抽象

**目标：** 用 `LLMClient` 适配器替换 [`_ask_llm`](../../../app/agent/service.py)，提供超时、有限重试、错误分类和调用指标（R-05），产出阶段 3 验收要求的"每个模型请求可通过 request ID 关联"。

### Task 2.1: LLMClient 与错误分类

**Files:**
- Create: `learn_da/app/agent/llm_client.py`
- Modify: `learn_da/config/settings.py`（新增 `LLM_TIMEOUT_SECONDS: float = 60`、`LLM_MAX_RETRIES: int = 1`）
- Test: `learn_da/tests/unit/test_llm_client.py`（新建）

- [x] **Step 1:** 定义结果模型与错误枚举：

```python
LLMErrorReason = Literal[
    "no_api_key", "auth_error", "rate_limited",
    "timeout", "upstream_error", "empty_response",
]

@dataclass(frozen=True)
class LLMResult:
    content: str | None
    error_reason: LLMErrorReason | None
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
```

- [x] **Step 2:** 实现 `LLMClient.complete(messages, tools=None, tool_choice=None) -> LLMResult`：
  - 总超时 `LLM_TIMEOUT_SECONDS`（`asyncio.timeout` 包裹）；
  - 仅对 `timeout / rate_limited / upstream_error` 重试，最多 `LLM_MAX_RETRIES` 次，指数退避；
  - `AuthenticationError -> auth_error`、`RateLimitError -> rate_limited`、`APITimeoutError -> timeout`、其余 API 异常 -> `upstream_error`、空 choices/content -> `empty_response`；
  - 每次调用记录结构化日志：request_id（`request_id_var`）、model、latency、tokens、error_reason。
- [x] **Step 3:** mock 各类异常写分类与重试次数断言测试（auth 不重试、429 重试一次等）。

### Task 2.2: AgentService 接入与 fallback_reason 透出

**Files:**
- Modify: `learn_da/app/agent/service.py`（删除 `_ask_llm`，注入 `LLMClient`）
- Modify: `learn_da/app/agent/schemas.py`（`AgentChatData` / `FixCodeResponse` / `ExplainCodeResponse` / `RecommendationGuidanceResponse` 新增 `fallback_reason: str | None = None`，`used_fallback=True` 时必填）
- Modify: `learn_da/app/agent/router.py`（依赖注入调整）
- Test: 更新现有 agent 单测 + 新增 fallback_reason 断言

- [x] **Step 1:** 四个入口全部改走 `LLMClient`；fallback 时把 `error_reason` 写入响应与日志。
- [x] **Step 2:** 在 chat 响应日志中补充 route、retrieval_mode（embedding/keyword/none）、knowledge 命中数。
- [x] **Step 3:** 全量回归（175 passed）+ 前端 `npm run build`（新增可选字段不破坏前端类型）。

**阶段 ② 验收标准：**
- 无 key、限流、超时、空响应四种场景在日志和响应 `fallback_reason` 中可区分。
- 单次请求的 route / retrieval mode / LLM latency / token / fallback reason 可通过 request ID 串联。
- 后端全量测试通过，`/agent/*` 对旧前端保持兼容。

---

## 阶段 ③：评测集基线

**目标：** 建立 roadmap 阶段 3 要求的离线评测集，量化当前关键词路由和检索质量，作为 ④ 的验收基线。**本阶段先于任何路由改动**（"评测先于 Agent 自主性"）。

### Task 3.1: 评测数据集

**Files:**
- Create: `learn_da/tests/eval/agent_intent_cases.yml`（30-50 条：`message`、`expected_intent`、`tags`）
- Create: `learn_da/tests/eval/agent_retrieval_cases.yml`（15-20 条：`query`、`expected_lesson_slug`）

- [x] **Step 1:** 意图用例必须覆盖：自然中文完整问句、意图冲突（"解释这个错误是什么意思"）、宽泛词误导（"这个函数怎么写"）、英文/中英混合、无明确意图闲聊。每条标注唯一期望意图（六选一）。
- [x] **Step 2:** 检索用例覆盖：中文整句（当前已知零召回场景）、单关键词、跨课程概念。期望值为 hit@3 命中课程 slug。

### Task 3.2: 评测 runner 与基线报告

**Files:**
- Create: `learn_da/scripts/eval_agent.py`（离线运行，输出意图准确率、检索 hit@3、分 tag 明细）
- Create: `learn_da/docs/agent-eval-baseline-2026-07.md`（记录基线数字）
- Test: `learn_da/tests/unit/test_eval_dataset.py`（校验用例文件 schema 合法、意图值域正确）

- [x] **Step 1:** runner 对每条用例调用 `AgentRouter.resolve()` 与 `KnowledgeRetriever._keyword_search()`（不调用外部 LLM/embedding，纯离线免费）。
- [x] **Step 2:** 输出并记录基线：关键词路由准确率 43.9%、关键词检索 hit@3 38.9%（详见 `docs/agent-eval-baseline-2026-07.md`）。
- [x] **Step 3:** 若配置了 embedding，可选运行 embedding 检索对比（runner 提供 `--with-embedding`，已在基线报告中标注为需要网络的手动步骤）。

**阶段 ③ 验收标准:**
- `python scripts/eval_agent.py` 可重复运行并输出稳定基线。
- 基线数字写入 `agent-eval-baseline-2026-07.md`，作为 ④ 的对比锚点。

---

## 阶段 ④：受限 Function Calling 改造

**目标：** 单入口 + 只读工具 + 硬步数上限的 FC 形态替换关键词路由与正则解析；同时一次性收口会话合约与取消传播。以 feature flag 灰度，评测通过才默认开启。

### 设计决策（实施者不需再决策）

| 决策点 | 结论 |
| --- | --- |
| 工具集 | `search_knowledge(query: str)`、`get_learner_progress()`、`get_recommendation()` 三个只读工具；visitor_id 由服务端注入，**不作为模型参数** |
| 步数上限 | `AGENT_FC_MAX_TOOL_ROUNDS = 2`；超限后强制 `tool_choice="none"` 要求直接回答 |
| 最终回答结构 | 保留 Markdown 文本 + 轻量意图标签（模型在 system prompt 中被要求首行不输出标签，意图取自其调用过的工具/显式声明字段）；不再用正则从文本抠结构 |
| 降级路径 | `settings.effective_llm_api_key` 为空或 FC flag 关闭时，走现有关键词路由 + 确定性 fallback，行为与 ③ 结束时完全一致 |
| flag | `AGENT_FC_ENABLED: bool = False`，环境变量控制 |
| 红线 | 不提供任何执行/写入类工具；`get_recommendation` 只读规则引擎结果，模型不得改排序 |

### Task 4.1: 工具定义与 FC 编排循环

**Files:**
- Create: `learn_da/app/agent/fc_tools.py`（OpenAI tools JSON schema + 工具执行器映射，执行器复用现有 `KnowledgeRetriever` / `LearnerStateService` / `RecommendationService`）
- Modify: `learn_da/app/agent/service.py`（新增 `chat_with_tools()`：LLMClient 带 tools 调用 → 解析 `tool_calls` → 执行 → 回传 `tool` 消息 → 循环，硬上限 2 轮）
- Modify: `learn_da/config/settings.py`（`AGENT_FC_ENABLED`、`AGENT_FC_MAX_TOOL_ROUNDS`）
- Test: `learn_da/tests/unit/test_agent_fc.py`（新建）

- [x] **Step 1:** 失败测试先行：mock LLM 依次返回 tool_call 与最终回答，断言工具被正确执行、超过 2 轮后强制收敛、未知工具名返回错误 tool 消息而不抛异常。
- [x] **Step 2:** 实现编排循环；每轮记录 tool 名、参数摘要、耗时到结构化日志。
- [x] **Step 3:** 工具参数用 Pydantic 校验，非法参数以错误 tool 消息回传给模型（一次机会），二次失败走 fallback。

### Task 4.2: /chat 入口切换与旧机制下线

**Files:**
- Modify: `learn_da/app/agent/router.py`（`/chat` 按 flag 分流：FC 路径 / 旧路径）
- Modify: `learn_da/app/agent/service.py`、`learn_da/app/agent/routing.py`（关键词路由仅在降级路径使用，注释明确其职责变更）
- Delete: `learn_da/app/agent/results.py` 正则解析（FC 默认开启后）；`learn_da/app/agent/tools.py` 保留 fallback 文案、删除 response_format 模板
- Modify: `/fix`、`/explain` 改为薄壳（组装消息后调 `chat_with_tools`），保留端点兼容前端快捷按钮

- [x] **Step 1:** flag 关闭时全量测试与 ③ 基线行为一致（回归护栏）。—— 201 passed，无 key/flag 关闭均走旧路径
- [x] **Step 2:** flag 开启时跑 ③ 评测集的 FC 版 runner（用真实或录制的 LLM 响应），意图准确率 ≥ 关键词基线才允许默认开启。—— 2026-07-28 首轮真实评测 37/41 = 90.2%，本次复核 38/41 = 92.7%，均高于关键词基线 18/41 = 43.9%（见 `docs/agent-eval-baseline-2026-07.md`）
- [x] **Step 3:** 默认开启后删除 `results.py` 与格式模板，更新 README 中"Function Calling"描述使其与实现一致（收口 R-09）。—— `AGENT_FC_ENABLED` 默认 `True`；`results.py` 已删除，`tools.py` 仅保留降级文案，根 README 与 docs README 已更新

### Task 4.3: 会话合约收口与取消传播

**Files:**
- Modify: `learn_da/app/agent/schemas.py`（明确 history 只含**已完成**的 user/assistant 消息，不含 tool 消息与当前消息；上限 20 条由后端裁剪）
- Modify: `learn_da_vue/src/components/agent/AgentPanel.vue`（history 构造排除当前正在发送的消息）
- Modify: `learn_da_vue/src/api/index.ts`（优先复用调用方传入的 AbortSignal，未提供时才自建 controller —— 修复 R-07）
- Test: `learn_da/tests/unit/test_agent_history_contract.py`（20 轮连续对话无 422、当前消息只出现一次）；前端 vitest 补取消传播断言

- [x] **Step 1:** 后端契约测试先行（模拟 20 轮，断言每轮 prompt 中当前 user 消息唯一）。
- [x] **Step 2:** 前端修复 + `npm run build` + vitest 通过。
- [ ] **Step 3:** 手测：点击"停止生成"后，Network 面板中请求实际 abort。

**阶段 ④ 验收标准：**
- FC 意图准确率 ≥ ③ 记录的关键词基线；检索 hit@3 不劣化。
- 无 key / flag 关闭时行为与 ③ 结束时逐字节一致（fallback 文案不变）。
- 20 轮对话无 422；取消后下游请求实际中断。
- 单次 FC 请求 ≤ 3 次 LLM 调用（2 轮工具 + 1 次最终回答），日志可完整追溯每轮。
- 模型无法触发任何写入或执行动作（工具集只读，代码审查确认）。

---

## 全局验证

每阶段合并前：

```
cd learn_da && .venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp
cd learn_da_vue && npm run build && npx vitest run
```

计划完成后新增 `docs/agent-refactor-fc-completion-summary.md` 并更新 `docs/README.md` 状态行（遵循清理约定）。

## 风险与回退

| 风险 | 缓解 |
| --- | --- |
| FC 意图准确率不及关键词基线 | flag 保持关闭，系统停留在 ③ 形态（已获得生命周期/可观测性收益），重新调工具描述后再评测 |
| embedding 缓存表膨胀 | 缓存键含模型名，切换模型时旧行可按 `model` 批量清理；课程量级（十余节）下无实际风险 |
| 前端对新增 `fallback_reason` 字段不兼容 | 字段为可选、仅新增，旧前端忽略即可 |
| FC 延迟高于单轮 | 步数上限 2 + 工具全部为本地/DB 只读调用（毫秒级），额外延迟主要来自第二次 LLM 往返，属可接受成本 |
