# Learn DA 文档入口

本文档用于快速判断项目当前状态、下一步行动和历史文档位置。

## 当前状态

- 2026-07-14 已完成全项目与 Agent 专项审查；当前成熟度判断为内部 Alpha，公开部署前应先完成安全执行、统一学习事实和工程门禁。
- Phase 3 已于 2026-07-14 完成整体收口；统一结论见 [`phase3-completion-summary.md`](phase3-completion-summary.md)。
- Phase 3 Round 1 已完成：建立学习建议服务、建议数据结构和课程元数据。
- Phase 3 Round 2 已完成：把默认顺学建议接入 Dashboard、Learning、LessonDetail。
- Phase 3 Round 3 已完成：补齐回补、分支、回流三类建议，并已补充核心自动化测试。
- Phase 3 Round 4 已完成：在规则建议之上增加 Agent 引导层，可解释当前推荐并生成一个小练习。
- 阶段 0 的“安全执行与交付门禁”设计已确认，详细实施计划已形成，等待选择执行方式。

## 下一步

Phase 3 不再新增任务。当前按“安全执行与交付门禁”实施计划推进阶段 0；完成安全验收后，再进入统一学习事实和简化学习主路径。

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

## 清理约定

- `completion-summary` 文档记录已完成轮次的设计、边界和验证结果。
- `changes` 文档只保留文件级改动摘要，不再继续扩写。
- `superpowers/plans` 下的计划文档是执行入口；若计划完成，应新增对应 completion summary，并在本页更新状态。
