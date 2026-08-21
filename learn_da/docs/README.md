# Learn DA 文档入口

本文档用于快速判断项目当前状态、下一步行动和历史文档位置。

## 当前状态

- 2026-07-14 已完成全项目与 Agent 专项审查；当前成熟度判断为内部 Alpha，公开部署前应先完成安全执行、统一学习事实和工程门禁。
- Phase 3 Round 1-4 已完成（建议服务、接入页面、回补/分支/回流、Agent 引导层）。
- 阶段 0 的"安全执行与交付门禁"已实施：独立 fail-closed Runner 服务、签名匿名 session cookie、Markdown 净化、快照治理与生产 HTTP 加固。Task 9（CI workflow、Mypy baseline 检查器、安全验收文档）尚未落地。
- 阶段 1 的"统一学习事实"已实施：`learner_state` 深模块、事件枚举与幂等键、前端统一状态来源、推荐与 Agent 输入收口、一次性重算脚本，并适配阶段 0 的签名 session 身份模型。后端 150 项测试、Runner 17 项、前端 24 项测试通过，前端 type-check 与生产构建通过。
- 阶段 1 复盘修复（2026-07-26）：补上 `.env` 漏配的 `learner_state` 模块开关（此前所有 learner-state 路由在真实环境不注册）、收口双写路径（`learner_state` 只保留读端点，状态变更统一走 `/analytics/track`）、补齐端点层契约测试，并首次实际验证阶段 1 迁移的升级 / 回滚与历史数据回填。
- Agent 重构与受限 Function Calling（2026-07-28）：阶段 ①②③、Task 4.1/4.2 与 4.3 Step 1/2 已完成；FC 意图评测收尾复核 92.7%（vs 关键词基线 43.9%，见 [`agent-eval-baseline-2026-07.md`](agent-eval-baseline-2026-07.md)）后 `AGENT_FC_ENABLED` 已默认开启。用户界面及公开 API 已进一步收口为唯一 `POST /agent/chat` 和两项上下文快捷动作（有错误时"解决当前报错"，否则"下一步怎么做"）；旧 `/agent/fix`、`/agent/explain`、`/agent/recommendation-guidance` 及其前端契约已删除。会话 history、调用方 AbortSignal 传播和浏览器 Network abort 已完成验证。
- 阶段 3 学习证据驱动 Agent（2026-07-31）：服务端证据解析器、结构化教学反馈契约、Agent 交互审计与 ai_help 关联、推荐证据聚合与 Dashboard 指标、离线评测与可靠性回归全部完成。Agent 的练习判断完全基于服务端数据库证据（五态：execution_failed / verification_failed / passed_unconfirmed / unverifiable / no_evidence），客户端自报 stdout/stderr/lastError 不再作为事实来源。`teachingFeedback` 的 state/attemptId/nextAction 由服务端决定，LLM 不得覆盖。`AgentInteraction` 表以 request_id 为幂等键，相同 ID 重放仅一条记录、一个 ai_help。完整总结见 [`phase3-evidence-agent-completion-summary.md`](phase3-evidence-agent-completion-summary.md)。
- 阶段 3 证据闭环修复（2026-08-01）：推荐主流程实际消费 Agent 证据聚合（帮助后仍未通过才触发回补）、`helpThenPassRate` 按 Attempt/练习/时间精确计算、无证据时不再把客户端 lesson 当作课程事实、模型调用前预留 request_id（重放不重复调用模型）、前端反馈按钮与 interactionId 关联、部署 Compose 自动执行 Alembic 迁移。
- 阶段 4 内容与界面规模化（2026-08-01）：Content Catalog 深模块（Pydantic schema 校验、引用图/无环校验、启动时一次构建的共享索引、`scripts/content_lint.py` 本地 lint、内容错误 fail closed）；前端核心工作流拆分为 `useLessonSession` / `usePlaygroundSession` / `useAgentConversation` 与 `RecommendationPanel`（三处建议统一）；删除失效基础设施（MinIO/Celery/邮件/Paramiko/Gevent/Redis、后端 ECharts package.json），限流保留 SlowAPI 单一实现。后端 390 项、前端 71 项测试通过。完整总结见 [`phase4-content-and-ui-completion-summary.md`](phase4-content-and-ui-completion-summary.md)。
- 生产部署验收（2026-08-17）：三节样板课程真实 Runner 执行 → 练习判定 → Attempt 幂等 → Agent 五态反馈 → 事件幂等 → Dashboard 指标全链路验收通过（17/17，脚本 `deploy/acceptance.sh`）。验收中发现并修复明文 HTTP 下会话 cookie 带 Secure 导致访客身份丢失的缺陷（新增 `PUBLIC_SCHEME` 配置）。记录见 [`production-acceptance-2026-08-17.md`](production-acceptance-2026-08-17.md)。
- 练习扩面（2026-08-20）：结构化练习从 3 节样板课扩展到全部 13 门课（每课 1 题）；validator 只用白名单（Polars 课 `dataframe_rows`、DuckDB/Python 课 `stdout_exact`），答案与 starter 均经本地真实判定链路双向验证（答案 passed、starter 不静默通过）。顺带修复沙箱镜像缺 `pyarrow` 导致第 11 课 Polars→DuckDB 桥（`to_arrow()`）无法运行的问题（`Dockerfile.sandbox` 新增 pyarrow；`deploy/update.sh` 会自动检测并重建沙箱镜像）。

## 写路径约定（阶段 1）

学习状态的**唯一写入口**是 `POST /analytics/track`：`AnalyticsService.track_event` 在同一事务内写事件日志并联动 `LearnerStateService` 投影。`/learner-state/*` 只提供读接口（`GET /learner-state/progress`）。前端所有完成 / 撤销 / 开始都带 `eventId` 上报，离线重试复用同一 `eventId` 以保证幂等。

## 下一步

- P1 收尾（2026-08-21）：① 回流建议信号移除对 CodeSnapshot 表的读取（快照功能已删，死表不再参与推荐打分）；② Agent 分级提示 hint_level 改为服务端真实连续求助计数（按课程统计 AgentInteraction：1-2 次 L1 / 3-4 次 L2 / 5+ L3），不再信任可伪造的客户端 history，查询不可用时降级为 history 估算。后端测试基线升至 399 项。

阶段 0、1、2、3、4 均已完成代码与测试闭环；生产部署验收已于 2026-08-17 通过（见验收记录）；结构化练习已于 2026-08-20 覆盖全部 13 门课。剩余事项：浏览器/移动端人工目测项、练习扩面后的生产部署（含沙箱镜像重建）。CI 暂缓：GitHub 账户账单锁定导致 Actions 无法运行，workflow 文件已于 2026-08-21 暂时移除（恢复：`git checkout ac779dc -- .github/workflows/ci.yml`），解锁账单前提交依赖本地手动测试。

## 文档地图

| 文档 | 用途 |
|---|---|
| [`project-review-2026-07-14.md`](project-review-2026-07-14.md) | 全项目审查：产品闭环、架构、数据、安全、部署与工程治理 |
| [`iteration-roadmap-2026-07-14.md`](iteration-roadmap-2026-07-14.md) | 后续迭代方向：阶段依赖、交付范围、验收标准与延后事项 |
| [`agent-system-review-2026-07-14.md`](agent-system-review-2026-07-14.md) | Agent 专项审查：真实能力、调用链、安全与可靠性风险 |
| [`superpowers/specs/2026-07-14-security-execution-delivery-gates-design.md`](superpowers/specs/2026-07-14-security-execution-delivery-gates-design.md) | 阶段 0 设计 Spec：安全执行、Web/API 信任边界和交付门禁 |
| [`superpowers/plans/2026-07-14-security-execution-delivery-gates.md`](superpowers/plans/2026-07-14-security-execution-delivery-gates.md) | 阶段 0 实施计划：9 个可独立验证的交付任务 |
| [`superpowers/plans/2026-07-31-phase3-evidence-aware-agent.md`](superpowers/plans/2026-07-31-phase3-evidence-aware-agent.md) | 阶段 3 执行入口：服务端练习证据、结构化教学反馈、审计与评测（已完成） |
| [`phase3-evidence-agent-completion-summary.md`](phase3-evidence-agent-completion-summary.md) | 阶段 3 学习证据驱动 Agent 收口：证据解析器、教学反馈、审计、推荐、评测 |
| [`superpowers/plans/2026-08-01-phase4-content-and-ui-scale.md`](superpowers/plans/2026-08-01-phase4-content-and-ui-scale.md) | 阶段 4 执行入口：Content Catalog、前端工作流拆分、失效基础设施清理（已完成） |
| [`phase4-content-and-ui-completion-summary.md`](phase4-content-and-ui-completion-summary.md) | 阶段 4 收口：内容索引、composable 拆分、依赖清理与本地验证 |
| [`production-acceptance-2026-08-17.md`](production-acceptance-2026-08-17.md) | 生产部署验收记录：17 项全链路检查、cookie 缺陷修复、遗留目测项 |

## 清理约定

- `completion-summary` 文档记录已完成轮次的设计、边界和验证结果。
- `changes` 文档只保留文件级改动摘要，不再继续扩写。
- `superpowers/plans` 下的计划文档是执行入口；若计划完成，应新增对应 completion summary，并在本页更新状态。
