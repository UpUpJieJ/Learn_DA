# 阶段 3：学习证据驱动的 Agent 具体实施计划

**状态：** 已完成（2026-07-31）
**制定日期：** 2026-07-31
**前置：** 阶段 2 的 `ExerciseAttempt`、确定性验证、Learner State、Dashboard
练习指标已完成。服务器部署验收单独处理，不阻塞本计划的本地开发与测试。

## 目标

把 Agent 从“前端把当前代码和报错拼入 prompt 的聊天框”收口为“服务端基于
课程、Attempt、验证结果和 Learner State 给出可解释的教学反馈”。

完成后，Agent 应能明确区分以下情况：

1. 代码执行失败；
2. 代码执行成功但确定性判定未通过；
3. 练习已通过但课程尚未确认完成；
4. Runner 不可用，结果不可验证；
5. 学习者没有任何可用练习证据。

## 已有基础，不重复建设

- `AgentService`、LLM client、`KnowledgeRetriever` 已在 lifespan 中复用；
- embedding 已按内容哈希持久化；
- LLM timeout、有限重试、错误分类和 fallback 已存在；
- history 契约、调用方 AbortSignal、受限 FC 与最多两轮工具调用已完成；
- `get_exercise_summary` 已是只读 FC 工具，且不会返回完整代码；
- 阶段 2 已持久化 `ExerciseAttempt`，并区分 `execution_status` 与
  `verification_status`。

本计划不新增代码执行类 Agent 工具，不让模型参与推荐排序，不引入多步自主
规划，也不实现 SSE。

## 设计约束

1. `visitor_id` 只能由服务端匿名会话注入，模型和客户端均不能指定。
2. Attempt、执行状态、验证状态、错误类型、已完成课程必须从数据库读取；
   客户端发送的同名字段不作为事实来源。
3. 自动注入给模型的是截断后的证据摘要，绝不自动注入历史 Attempt 的完整代码。
   当前编辑器代码仍可由用户显式请求解释或排错。
4. Agent 请求、`ai_help`、Attempt 和结果指标必须使用稳定 request ID 关联，
   重放不得重复计数。
5. 当服务端证据与客户端显示不一致时，以服务端证据为准，并在反馈中说明
   “结果以最近一次已保存的尝试为准”。

## 交付顺序

```text
Task 1 服务端证据解析器
  -> Task 2 结构化反馈契约与提示策略
  -> Task 3 单一 Agent 写入与审计模型
  -> Task 4 前端展示与快捷动作
  -> Task 5 离线评测与端到端回归
  -> Task 6 文档与发布验收
```

## Task 1：建立服务端练习证据解析器

**目的：** 每次 Agent chat 在调用模型前，按服务端身份构造可信教学上下文。

**文件：**

- 新增 `app/agent/evidence.py`
- 修改 `app/practice/repository.py`
- 修改 `app/practice/service.py`
- 修改 `app/agent/router.py`
- 修改 `app/agent/service.py`
- 新增 `tests/unit/test_agent_evidence.py`

**实现：**

1. 定义 `AgentLearningEvidence`，字段包含 `lesson_slug`、`exercise_id`、
   `attempt_id`、`execution_status`、`verification_status`、`failure_reason`、
   `duration_ms`、有限长度的 stdout/stderr 摘要、课程完成状态和证据时间。
2. `PracticeRepository` 增加按 `(visitor_id, attempt_id)` 查询，及按
   `(visitor_id, lesson_slug)` 查询最近 Attempt 的显式方法；禁止跨 visitor 查询。
3. `AgentEvidenceResolver` 接受 visitor、可选 lesson slug、可选 attempt ID，
   依次解析：指定 Attempt -> 该课程最近 Attempt -> 无 Attempt。
4. 请求体只保留 `currentLesson` 和可选 `attemptId` 作为定位线索；服务端校验
   lesson 和 attempt 的归属关系。移除或标记 `stdout`、`stderr`、`lastError`
   的事实语义，避免伪造状态进入教学判断。
5. 在 FC prompt 的 system evidence block 中始终写入解析结果；模型仍可按需调用
   `get_exercise_summary` 取得最近多次摘要，但不能越权读取完整 Attempt。

**测试：**

- 伪造 `attemptId`、lesson slug 或验证状态不能影响其他 visitor 的反馈；
- 代码成功与验证通过分别进入不同 evidence 分支；
- `unverifiable/runner_unavailable` 不进入“代码错误”提示；
- 无 Attempt 时不构造虚假失败上下文；
- 自动上下文不包含历史 Attempt 的 `code` 字段。

**验收：** Agent 的判断证据可由数据库记录复现，前端无法伪造“已经通过”或
“Runner 报错”。

## Task 2：定义结构化教学反馈与分级提示

**目的：** 让 API 和 UI 消费稳定的教学结论，而不是从 Markdown 文本猜测状态。

**文件：**

- 修改 `app/agent/schemas.py`
- 修改 `app/agent/prompts.py`
- 修改 `app/agent/service.py`
- 修改 `learn_da_vue/src/types/api.ts`
- 修改 `learn_da_vue/src/api/agent.ts`
- 修改 `learn_da_vue/src/components/agent/AgentPanel.vue`
- 新增 `tests/unit/test_agent_feedback.py`
- 新增或扩展前端 Agent API/组件测试

**契约：** `AgentChatData` 新增可选 `teachingFeedback`，至少包括：

```json
{
  "state": "execution_failed | verification_failed | passed_unconfirmed | unverifiable | no_evidence",
  "attemptId": 42,
  "evidenceSummary": "最近一次运行成功，但练习断言未通过",
  "diagnosis": "...",
  "hintLevel": 1,
  "nextAction": "inspect_result | retry_exercise | confirm_lesson | retry_later"
}
```

**实现：**

1. `state`、`attemptId` 和 `nextAction` 由服务端 evidence resolver 决定，LLM
   不得覆盖。
2. LLM 只生成 `diagnosis` 与与 `hintLevel` 对应的教学文案；无 LLM 时生成同一
   schema 的确定性 fallback。
3. 提示默认从 Level 1（定位概念/错误）开始；连续求助才逐级升高，最高层级
   仍先解释思路，不直接写出完整答案。
4. 前端以 `teachingFeedback` 渲染状态、证据摘要和下一步按钮；Markdown 内容
   仅作为解释正文，不能决定按钮行为。

**测试：**

- 五种 evidence state 均有 LLM 与 fallback 返回值测试；
- 模型给出冲突 JSON 或不当完整答案时，服务端保留权威 state 并降级；
- UI 对不同 `nextAction` 显示正确动作，长文本和移动端不溢出。

**验收：** 练习通过、运行失败、验证失败和不可验证在 Agent UI 中有不同且可
审计的状态，不再只显示泛化聊天文本。

## Task 3：持久化 Agent 交互审计与 `ai_help` 关联

**目的：** 使 Agent 使用、练习结果和推荐影响可跨进程查询、统计与回放。

**文件：**

- 新增 `app/agent/models.py` 的 `AgentInteraction`（保留既有 embedding model）
- 新增 Alembic migration
- 新增 `app/agent/repository.py`
- 修改 `app/agent/router.py`
- 修改 `app/agent/service.py`
- 修改 `app/analytics/router.py` 或新增只读 Agent analytics endpoint
- 新增 `tests/unit/test_agent_interaction_repository.py`
- 新增 `tests/unit/test_agent_interaction_api.py`

**数据模型：**

- `request_id`：唯一幂等键；
- `visitor_id`、`lesson_slug`、`attempt_id`：可为空但必须校验归属；
- `route`、`retrieval_mode`、`tool_names`；
- `llm_latency_ms`、`input_tokens`、`output_tokens`、`fallback_reason`；
- `evidence_state`、`verification_status`、`hint_level`、`next_action`；
- `feedback`：用户之后点击“有帮助/无帮助”时更新的有限枚举。

**实现：**

1. 为 `/agent/chat` 生成或接收 request ID；同一 ID 的重试只返回已有交互结果，
   不重复调用模型、不重复增加 `ai_help`。
2. 将 `AgentInteraction` 与 `ai_help` 写入同一数据库事务；`ai_help` 的 lesson
   和 attempt 关联来自 evidence resolver，而不是客户端上下文。
3. LLM、工具和 fallback 指标在响应完成后写入审计表；不得持久化完整 prompt、
   完整代码、Runner token 或会话 cookie。
4. 增加“用户反馈”只写接口，校验 interaction 属于当前 visitor，且同一反馈可
   覆盖更新但不得新增 `ai_help`。

**测试：**

- 相同 request ID 并发/重放后仅一条 interaction、一个 `ai_help`；
- 伪造 `attemptId` 得不到其他 visitor 的审计或反馈权限；
- fallback、429、timeout、tool 参数错误均持久化对应分类；
- 审计摘要中不存在代码、token、cookie 和完整 LLM 内容。

**验收：** 从一个 request ID 可追溯用户动作、证据、检索、模型成本、反馈与
后续验证结果。

## Task 4：接入推荐和前端工作流

**目的：** 让 Agent 反馈影响下一步建议，但不改变规则推荐的排序权。

**文件：**

- 修改 `app/learning/recommendation.py`
- 修改 `app/analytics/router.py`
- 修改 `learn_da_vue/src/views/Playground.vue`
- 修改 `learn_da_vue/src/components/agent/AgentPanel.vue`
- 修改或新增 `learn_da_vue/src/stores/*`
- 扩展 `tests/unit/test_recommendation_*.py`

**实现：**

1. 推荐规则读取已聚合的 Attempt/Agent interaction 摘要，例如“验证失败后已获
   Level 2 提示但仍未通过”，而不是把聊天次数简单当作困难度。
2. `retry_exercise` 跳转/聚焦当前练习并恢复草稿；`confirm_lesson` 只提出建议，
   保留既有用户确认完成语义。
3. Dashboard 增加帮助后通过率、未解决验证失败数等真实指标；数据为空时保持
   安静降级，不显示虚假百分比。

**测试：**

- Agent 多次求助但无 Attempt 不触发错误的回补推荐；
- 验证失败 + 后续通过可计算“帮助后通过”；
- 同一 Interaction 重放不改变推荐或 Dashboard 聚合。

**验收：** RecommendationService 仍是唯一排序来源，Agent 只提供证据和解释。

## Task 5：离线评测、可靠性回归和浏览器验收

**目的：** 用可重复的证据验证 Agent 的教学效果与故障边界。

**文件：**

- 新增 `tests/eval/agent_evidence_cases.yml`（30-50 条）
- 修改 `scripts/eval_agent.py`
- 新增 `tests/integration/test_agent_evidence_flow.py`
- 新增/扩展前端 Vitest 与浏览器 E2E 用例
- 新增 `docs/agent-evidence-eval-baseline-2026-07.md`

**评测维度：**

1. evidence state 分类正确率；
2. Attempt 归属隔离；
3. 课程知识召回；
4. 提示优先级和不直接给答案；
5. 修复建议后的下一次确定性验证通过率；
6. 推荐下一步是否遵循服务端规则；
7. timeout、429、upstream error、取消和 fallback 的可观测分类。

**强制回归：**

- 20 轮 history，当前消息不重复；
- AbortSignal 取消不产生新的 interaction 或 UI 回写；
- 限流 429、模型 timeout、Runner unavailable 均返回稳定 schema；
- 真实或受控 Runner 下覆盖 Python Functions、Polars Basics、DuckDB SQL
  Foundations 的五种 evidence state；
- 后端全量、Runner 全量、前端 Vitest、前端生产构建、Alembic 升降级均通过。

**验收：** 每项阶段三验收标准都有测试、评测报告或浏览器证据，不能只凭日志
或手工聊天截图宣布完成。

## Task 6：文档、发布门槛和收口

**文件：**

- 新增 `docs/phase3-evidence-agent-completion-summary.md`
- 修改 `docs/README.md`
- 修改根目录 `README.md` 的 Agent 与部署说明

**发布门槛：**

1. 完成数据库迁移升级、降级、再升级验证；
2. 所有 Agent interaction 的敏感字段审计通过；
3. 评测报告记录基线、通过条件和已知失败类型；
4. 服务器部署恢复后，三节样板课程均完成真实 Runner 执行、Agent 反馈和
   Dashboard 指标验收；
5. 将生产部署、密钥轮换、Runner 主机隔离风险写入运维文档。

## 完成定义

阶段三只有同时满足下列条件才可标记完成：

- Agent 的练习判断完全基于服务端证据；
- 五种学习状态均产生稳定结构化反馈与安全 fallback；
- `ai_help`、Agent interaction、Attempt、验证和用户反馈可通过 request ID
  串联且幂等；
- 推荐继续由规则服务排序；
- 评测、E2E、迁移和全量回归都有可复现通过证据；
- 不存在模型可直接执行代码、读取其他 visitor Attempt 或用前端伪造状态改变
  教学结论的路径。
