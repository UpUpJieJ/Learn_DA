# 阶段 3：学习证据驱动 Agent 完成总结

**状态：** 已完成
**完成日期：** 2026-07-31
**计划入口：** [`superpowers/plans/2026-07-31-phase3-evidence-aware-agent.md`](superpowers/plans/2026-07-31-phase3-evidence-aware-agent.md)

## 目标回顾

把 Agent 从"前端把当前代码和报错拼入 prompt 的聊天框"收口为"服务端基于
课程、Attempt、验证结果和 Learner State 给出可解释的教学反馈"。

## 交付物

### Task 1：服务端练习证据解析器

- 新增 `app/agent/evidence.py`：`AgentLearningEvidence` 数据契约 +
  `AgentEvidenceResolver`（按 visitor、可选 lesson slug、可选 attempt ID
  依次解析：指定 Attempt → 课程最近 Attempt → 无 Attempt）。
- `PracticeRepository` 新增 `get_latest_by_lesson(visitor_id, lesson_slug)`，
  始终带 visitor 过滤，禁止跨 visitor 查询。
- `AgentContext` 新增 `attemptId`；`stdout`/`stderr`/`lastError` 标记为
  非事实来源（不再注入 prompt context block），练习状态由服务端证据块提供。
- `AgentService._inject_evidence` 在 FC 与降级路径均注入服务端证据块。
- 证据五态：`execution_failed` / `verification_failed` /
  `passed_unconfirmed` / `unverifiable` / `no_evidence`。
- 证据不包含历史 Attempt 的 `code` 字段；stdout/stderr 截断为 500 字摘要。

### Task 2：结构化教学反馈契约与分级提示

- `AgentChatData` 新增 `teachingFeedback`：`state` / `attemptId` /
  `evidenceSummary` / `diagnosis` / `hintLevel` / `nextAction`。
- `state` / `attemptId` / `nextAction` 由服务端 evidence resolver 决定，
  LLM 不得覆盖；LLM 只生成 `content` 正文（与 hintLevel 对应的教学文案）。
- `nextAction` 枚举：`inspect_result` / `retry_exercise` / `confirm_lesson`
  / `retry_later`。
- 分级提示：Level 1 起步，连续求助（history user 消息增多）逐级升高至 Level 3，
  最高层级仍先解释思路，不直接给完整答案。
- 前端 `AgentPanel.vue` 渲染状态徽章、证据摘要、提示层级和下一步动作按钮
  （floating + embedded 双模式）。

### Task 3：Agent 交互审计与 ai_help 关联

- 新增 `AgentInteraction` 模型（`app/agent/models.py`）与迁移
  `c3f8a1b7e2d4_phase3_agent_interactions.py`。
- 新增 `AgentInteractionRepository`（`app/agent/repository.py`）：
  `get_or_create` 幂等（相同 request_id 重放仅一条记录、一个 ai_help）；
  `fill_metrics` 回填路由/检索/工具/延迟/token/降级/证据/反馈指标；
  `update_feedback` upsert 用户反馈。
- `AgentService` 在模型调用前预留 interaction，完成后在同一事务回填指标并写入
  ai_help；无 Attempt 时不把客户端 lesson slug 作为课程事实。
- 新增 `POST /agent/feedback` 端点：校验 interaction 归属当前 visitor，
  可覆盖更新但不新增 ai_help。
- 审计记录不持久化完整 prompt、完整代码、Runner token 或会话 cookie。

### Task 4：接入推荐和前端工作流

- `RecommendationService` 新增 `interaction_repo` 依赖与
  `_get_agent_help_summary`（读取帮助后仍未通过的聚合信号）。
- 回补推荐规则修正：Agent 多次求助但无任何练习活动（code_runs=0 且
  snapshots=0）不触发回补——仅提问未实践不构成学习困难证据。
- `AnalyticsService` practice-stats 端点新增 `helpThenPassRate`（帮助后通过率）
  与 `unresolvedFailures`（未解决失败数），无数据时降级为 None。
- 前端 `confirm_lesson` 按钮只提出建议（发送 Agent 消息），保留既有用户
  确认完成语义；`retry_exercise` 聚焦 Playground 编辑器。

### Task 5：离线评测、可靠性回归和浏览器验收

- 新增 `tests/eval/phase3_evidence_cases.yml`：31 条评测用例，覆盖 7 个维度
  （证据准确率、下一步动作、分级提示、代码泄露、fallback 分类、游客隔离、
  Runner 不可用）。
- 新增 `tests/unit/test_agent_eval.py`：参数化离线评测 harness，对每条 case
  做证据推导 + 反馈契约 + 代码泄露断言。
- 新增 `tests/integration/test_agent_reliability.py`：可靠性回归（长 history、
  空消息 422、timeout fallback、Runner 不可用 no_evidence、反馈端点归属校验、
  并发不阻塞）。
- 新增 `learn_da_vue/src/api/agent-feedback.spec.ts`：前端教学反馈类型契约
  测试（五态、四动作、null/undefined 兼容、代码不泄露）。

### Task 6：文档、发布门槛和收口

- 本完成总结。
- `docs/README.md` 状态与文档地图更新。
- 根 `README.md` Agent 说明补充证据驱动能力。

## 验证证据

| 门槛 | 结果 |
|---|---|
| 迁移升级 → 降级 → 再升级 | 通过（`c3f8a1b7e2d4` 单一 head） |
| 敏感字段审计 | `AgentInteraction` 无 code/prompt/cookie/token 列；证据序列化无 code |
| 离线评测 | 31 条 case 的证据、反馈和代码隔离断言通过；归属隔离由独立测试覆盖 |
| 单元测试 | 后端 374 项通过 |
| 前端测试 | 47 项通过（7 文件） |
| 前端类型检查 | `vue-tsc --noEmit` 通过 |
| 前端生产构建 | `npm run build` 通过 |
| 可靠性回归 | 7 项集成测试通过（history/422/timeout/Runner/feedback/并发） |

## 安全边界

- `visitor_id` 只能由服务端匿名会话注入，模型和客户端均不能指定。
- Attempt / 执行状态 / 验证状态 / 错误类型 / 已完成课程必须从数据库读取，
  客户端自报值不影响教学判断。
- 伪造 `attemptId` 或 lesson slug 得不到他人证据（跨 visitor 查询被拒）。
- `request_id` 全局唯一幂等键：相同 ID 重放不再次调用模型，仅保留一条 interaction、一个 ai_help，返回原交互 ID。
- 自动注入的是截断证据摘要，绝不自动注入历史 Attempt 完整代码。
- 不新增代码执行类 Agent 工具，不让模型参与推荐排序，不实现 SSE，
  不引入多步自主规划。

## 已知限制

- `_estimate_hint_level` 以当前请求 history 的 user 消息数近似连续求助计数；
  Task 3 的 `AgentInteraction` 表已就绪，后续可改为按真实持久化计数。
- 历史 interaction 缺少 attempt_id 时不参与 `helpThenPassRate`，避免用课程粒度猜测；
  新交互按 Attempt、exercise_id 和时间顺序计算。
- 服务器部署验收（三节样板课程真实 Runner 执行 + Agent 反馈 + Dashboard 指标）
  需在部署恢复后单独完成，不阻塞本地开发与测试。
