# Learn DA Phase 3 完成总结

完成日期：2026-07-14

## 阶段目标

Phase 3 建立了一套规则驱动、可解释、可降级的学习建议系统，并在规则建议之上增加 Agent 引导层。系统能够根据课程元数据、学习进度和 analytics 行为数据回答两个问题：下一步学什么，以及为什么现在适合学它。

## 四轮交付

| 轮次 | 核心交付 | 状态 |
|---|---|---|
| Round 1 | 课程元数据、统一建议数据结构、RecommendationService 骨架 | 已完成 |
| Round 2 | 默认顺学建议，以及 Dashboard、Learning、LessonDetail 页面接入 | 已完成 |
| Round 3 | 回补、分支、回流建议，优先级链、冷却和恢复成本模型 | 已完成 |
| Round 4 | Agent 推荐解释、小练习、确定性 fallback 和前端快捷动作 | 已完成 |

## 最终能力

RecommendationService 统一输出四类建议：

1. `next_lesson`：正常推进时推荐下一课。
2. `review_lesson`：检测到学习困难时推荐前置课程。
3. `branch_path`：完成分支点后提供可选学习方向。
4. `resume_session`：长时间未学习时推荐恢复成本最低的课程。

规则建议通过 `GET /api/v1/recommendations` 提供。Agent 引导通过 `POST /api/v1/agent/recommendation-guidance` 获取同一条规则建议，再生成学习者可读的解释和一个 5 到 10 分钟的小练习。没有可用 LLM 时，接口返回确定性 fallback。

## 架构结论

```text
课程元数据 + 完成进度 + analytics 行为
                    |
                    v
        RecommendationService
        回补 > 分支 > 回流 > 顺学
                    |
          +---------+---------+
          |                   |
          v                   v
  页面建议卡片        Agent guidance
                      解释 + 小练习
```

- RecommendationService 是推荐类型、目标和优先级的唯一来源。
- Agent 只负责解释和练习引导，不参与推荐排序。
- 无 analytics 时回补、回流自然降级；无 LLM 时 Agent guidance 使用确定性文本。
- 本阶段没有引入黑盒推荐、长期用户偏好画像或新的 analytics 表。

## 主要交付物

- 后端：`app/learning/recommendation.py`、learning recommendation API、Agent guidance schema/prompt/service/endpoint。
- 前端：建议 API 与类型、三处建议展示、Agent 面板“解释推荐”快捷动作。
- 内容：课程 frontmatter 中的 track、prerequisites、recommended_next、skill_tags、review/branch 标记。
- 配置：回补阈值、冷却时间和回流间隔均可通过环境变量调整。
- 文档：Round 1-4 完成总结及 2026-07-13 Round 4 已完成计划。

## 验证证据

- `tests/unit/test_recommendation_phase3.py` 覆盖回补、冷却、配置阈值、分支和回流成本。
- API 集成测试通过真实 SQLAlchemy 模型和测试数据库验证 analytics 写入后的回补、回流响应。
- `tests/unit/test_recommendation_generalization.py` 验证非数据分析主题的顺学与通用分支能力。
- `tests/unit/test_agent_recommendation_guidance.py` 覆盖 schema、prompt、LLM 解析、fallback 和 endpoint。
- Phase 3 聚焦测试：`15 passed`。
- 项目后端全量测试：`79 passed`。
- 前端 `npm run build` 通过，包含 Vue TypeScript 检查和 Vite 生产构建。

## 收口边界

以下事项不再作为 Phase 3 未完成任务：

- 基于生产用户数据继续调整默认阈值，属于运营调优。
- 浏览器视觉 E2E、跨浏览器矩阵和截图回归，属于后续质量建设。
- 推荐效果埋点、实验分析和长期偏好画像，需要独立产品计划。
- 新的学习主题、推荐类型或 LLM 排序能力，需要在下一阶段单独立项。

Phase 3 至此完成，不再从历史计划文档推导新增待办。
