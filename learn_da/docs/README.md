# Learn DA 文档入口

本文档用于快速判断项目当前状态、下一步行动和历史文档位置。

## 当前状态

- Phase 3 已于 2026-07-14 完成整体收口；统一结论见 [`phase3-completion-summary.md`](phase3-completion-summary.md)。
- Phase 3 Round 1 已完成：建立学习建议服务、建议数据结构和课程元数据。
- Phase 3 Round 2 已完成：把默认顺学建议接入 Dashboard、Learning、LessonDetail。
- Phase 3 Round 3 已完成：补齐回补、分支、回流三类建议，并已补充核心自动化测试。
- Phase 3 Round 4 已完成：在规则建议之上增加 Agent 引导层，可解释当前推荐并生成一个小练习。
- 当前没有活跃实施计划；后续工作应单独立项，不再从历史计划推断待办。

## 下一步

Phase 3 不再新增任务。下一阶段应根据新的产品目标建立独立计划，并在开始实施时更新本页。

## 文档地图

| 文档 | 用途 |
|---|---|
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
