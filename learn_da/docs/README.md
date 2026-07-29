# Learn DA 文档入口

本文档用于快速判断项目当前状态、下一步行动和历史文档位置。

## 当前状态

- 2026-07-14 已完成全项目与 Agent 专项审查；当前成熟度判断为内部 Alpha，公开部署前应先完成安全执行、统一学习事实和工程门禁。
- Phase 3 Round 1-4 已完成（建议服务、接入页面、回补/分支/回流、Agent 引导层）。
- 阶段 0 的“安全执行与交付门禁”已实施：独立 fail-closed Runner 服务、签名匿名 session cookie、Markdown 净化、快照治理与生产 HTTP 加固。Task 9（CI workflow、Mypy baseline 检查器、安全验收文档）尚未落地。
- 阶段 1 的“统一学习事实”已实施：`learner_state` 深模块、事件枚举与幂等键、前端统一状态来源、推荐与 Agent 输入收口、一次性重算脚本，并适配阶段 0 的签名 session 身份模型。后端 150 项测试、Runner 17 项、前端 24 项测试通过，前端 type-check 与生产构建通过。
- 阶段 1 复盘修复（2026-07-26）：补上 `.env` 漏配的 `learner_state` 模块开关（此前所有 learner-state 路由在真实环境不注册）、收口双写路径（`learner_state` 只保留读端点，状态变更统一走 `/analytics/track`）、补齐端点层契约测试，并首次实际验证阶段 1 迁移的升级 / 回滚与历史数据回填。
- Agent 重构与受限 Function Calling（2026-07-28）：阶段 ①②③、Task 4.1/4.2 与 4.3 Step 1/2 已完成；FC 意图评测收尾复核 92.7%（vs 关键词基线 43.9%，见 [`agent-eval-baseline-2026-07.md`](agent-eval-baseline-2026-07.md)）后 `AGENT_FC_ENABLED` 已默认开启。用户界面及公开 API 已进一步收口为唯一 `POST /agent/chat` 和两项上下文快捷动作（有错误时“解决当前报错”，否则“下一步怎么做”）；旧 `/agent/fix`、`/agent/explain`、`/agent/recommendation-guidance` 及其前端契约已删除。会话 history、调用方 AbortSignal 传播和浏览器 Network abort 已完成验证。

## 写路径约定（阶段 1）

学习状态的**唯一写入口**是 `POST /analytics/track`：`AnalyticsService.track_event` 在同一事务内写事件日志并联动 `LearnerStateService` 投影。`/learner-state/*` 只提供读接口（`GET /learner-state/progress`）。前端所有完成 / 撤销 / 开始都带 `eventId` 上报，离线重试复用同一 `eventId` 以保证幂等。

## 下一步

阶段 0、1 已基本完成。Task 9（CI/mypy baseline/安全验收文档）按当前决策不实施。下一步进入阶段 2（可验证练习闭环）或阶段 3（Agent 可靠性）；Agent Function Calling 重构与功能收口已完成。

## 文档地图

| 文档 | 用途 |
|---|---|
| [`project-review-2026-07-14.md`](project-review-2026-07-14.md) | 全项目审查：产品闭环、架构、数据、安全、部署与工程治理 |
| [`iteration-roadmap-2026-07-14.md`](iteration-roadmap-2026-07-14.md) | 后续迭代方向：阶段依赖、交付范围、验收标准与延后事项 |
| [`agent-system-review-2026-07-14.md`](agent-system-review-2026-07-14.md) | Agent 专项审查：真实能力、调用链、安全与可靠性风险 |
| [`superpowers/specs/2026-07-14-security-execution-delivery-gates-design.md`](superpowers/specs/2026-07-14-security-execution-delivery-gates-design.md) | 阶段 0 设计 Spec：安全执行、Web/API 信任边界和交付门禁 |
| [`superpowers/plans/2026-07-14-security-execution-delivery-gates.md`](superpowers/plans/2026-07-14-security-execution-delivery-gates.md) | 阶段 0 实施计划：9 个可独立验证的交付任务 |
| [`phase3-completion-summary.md`](phase3-completion-summary.md) | Phase 3 整体收口：目标、架构、交付物、验证与边界 |
| [`phase3-round1-completion-summary.md`](phase3-round1-completion-summary.md) | Round 1 完整总结：建议骨架与元数据 |
| [`phase3-round1-changes.md`](phase3-round1-changes.md) | Round 1 文件级改动清单 |
| [`phase3-round2-completion-summary.md`](phase3-round2-completion-summary.md) | Round 2 完整总结：默认顺学建议接入页面 |
| [`phase3-round2-changes.md`](phase3-round2-changes.md) | Round 2 文件级改动清单 |
| [`phase3-round3-completion-summary.md`](phase3-round3-completion-summary.md) | Round 3 完整总结：回补、分支、回流建议 |
| [`phase3-round4-completion-summary.md`](phase3-round4-completion-summary.md) | Round 4 完整总结：Agent 推荐解释与练习引导 |
| [`superpowers/plans/2026-07-13-round4-agent-recommendations.md`](superpowers/plans/2026-07-13-round4-agent-recommendations.md) | Round 4 已完成实施计划 |
| [`superpowers/plans/2026-07-28-agent-refactor-function-calling.md`](superpowers/plans/2026-07-28-agent-refactor-function-calling.md) | Agent 重构与受限 Function Calling 实施计划（执行入口，进行中） |

## 清理约定

- `completion-summary` 文档记录已完成轮次的设计、边界和验证结果。
- `changes` 文档只保留文件级改动摘要，不再继续扩写。
- `superpowers/plans` 下的计划文档是执行入口；若计划完成，应新增对应 completion summary，并在本页更新状态。
