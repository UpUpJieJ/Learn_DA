# Learn DA 文档入口

更新于 2026-11-01。当前项目使用课程工作区、服务端可信判定和真实 Docker Runner，已完成正式部署。工程状态与架构约定以 [AGENTS.md](../../AGENTS.md) 为准，日常操作使用[部署与运维手册](../../deploy/README.md)。

## 现用文档

| 文档 | 用途 |
| --- | --- |
| [部署与运维手册](../../deploy/README.md) | 日常更新、配置、备份恢复、故障排查、Hermes 启停 |
| [Docker 镜像排查](../../deploy/DOCKER_MIRROR.md) | 镜像标签、registry 与软件源问题 |
| [2026-11-01 部署记录](deployment-2026-11-01.md) | 运行源码版本、镜像 ID、迁移 head、29 项验收及 76 项课程执行证据 |
| [工作区内容规范](workspace-content-spec.md) | 课程 frontmatter、结构化断言、数据集与参考结果的写作规则 |
| [学习工作区设计与阶段记录](learning-workspace-redesign-2026-10-21.md) | 工作区和页面改版的设计依据；执行现状见收口记录 |
| [重构收口记录](refactor-closeout-2026-10-31.md) | 可信判定、并发、学习事件、SSE、前端状态和部署兼容事项 |
| [最近重构审查](refactor-review-2026-10-26.md) | 已修复问题的原始复现与安全证据，不能当作当前缺陷清单 |
| [最近重构执行记录](superpowers/plans/2026-10-31-refactor-closeout.md) | 最近一次重构的范围、决策和验证记录 |

## 当前实现约定

- 工作区入口是 `/lesson/:slug`，课程地图是 `/learn`，进度与报告来自 `/workspace/progress`、`/workspace/report`。
- Runner 回传有界 observations，后端依据课程契约和 refs 进行可信判定；课程使用 `frame_equal/schema/sql_rows/value/call`，不再新增 `expr_true`。
- 教学证据来自 `task_attempts`。学习事件复用 AnalyticsService 与 LearnerState 投影规则；旧 `exercise_attempts` 和 `code_snapshots` 仅保留模型与历史表，不恢复旧写入链路。
- AI 助手只读服务端证据，聊天用真 SSE，阶梯提示由服务端真实记录决定；不自行规划学习路线。
- 日常更新保留数据。生产模式只允许 Docker；CI 恢复前，代码提交依赖本地完整测试与生产构建验证。

## 仍在使用的脚本

路径相对 `learn_da/`，除最后一项外均为常用检查入口：

| 脚本 | 用途 |
| --- | --- |
| `scripts/content_lint.py` | 内容和目录校验 |
| `scripts/build_datasets.py --check` | 数据集可复现性校验 |
| `scripts/build_expected.py --check` | refs 与参考解一致性校验 |
| `scripts/verify_workspace.py` | 会创建验收会话的工作区端到端自检 |
| `scripts/verify_observation_runner.py` | 不写学习库的全部课程 Docker 契约检查 |
| `scripts/eval_agent.py` | 当前数据集的离线意图/检索评测，联网模式需显式选择 |
| `scripts/recompute_learner_state.py` | 历史学习事件投影重算，默认干跑，修复场景才使用 --write |

Runner 的 `scripts/poc_judgement_bypass.py` 与对应 pytest 保留为越权回归证据。迁移、模型登记、命令行维护脚本不因没有前端调用而视为孤儿。

## 历史依据

以下资料保留的是特定日期的审查结论与设计决策，涉及的旧页面、快照、练习 API 和待办状态已有后续变更：

- [2026-07 全项目审查](project-review-2026-07-14.md)
- [2026-07 Agent 审查](agent-system-review-2026-07-14.md)
- [已完成的阶段路线图](iteration-roadmap-2026-07-14.md)
- [早期安全边界设计](superpowers/specs/2026-07-14-security-execution-delivery-gates-design.md)
- [旧评测集基线](agent-eval-baseline-2026-07.md)：只适用于当时的数据集，当前指标需重新运行评测

旧练习体系的设计/验收说明、被现用设计取代的执行清单及重复完成总结已从工作树删除；需要追溯时从 Git 历史查看，不复制旧命令作为当前操作步骤。新文档应优先更新现有入口，避免重复保存互相矛盾的“当前状态”。
