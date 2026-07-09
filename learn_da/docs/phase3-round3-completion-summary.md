# Learn DA 第三阶段第三轮实施总结

**实施时间**: 2026-06-08（随 `0e2ecaf Complete general topic phase 3` 提交落地）
**实施范围**: 阶段 3 - 回补 / 分支 / 回流建议
**对应任务**: 第三阶段计划中的 Task 3.1、3.2、3.3
**前置轮次**: Round 1（建议骨架）、Round 2（默认顺学建议接入）

> 注：本轮代码随「通用编程主题 phase 3」提交一并落地，但未单独撰写完成总结，导致文档与代码一度脱节。本文档为事后补齐，内容对齐当前 `main` 上的真实实现。

---

## 一、实施目标

在 Round 2「默认顺学建议」跑通的基础上，补齐第三阶段预留的三类高阶建议，让建议系统覆盖更真实的学习场景：卡住时回补、路径分叉时分支、长时间未学时回流。

核心原则（延续前两轮）：
- ✅ 规则驱动、可解释，每条建议都有明确理由
- ✅ 复用 Round 1 的统一数据结构（`LearningRecommendation` / `RecommendationResponse`）
- ✅ 优先级链路清晰：回补 > 分支 > 回流 > 顺学
- ❌ 不引入 Agent 主导推荐（留到 Round 4）
- ❌ 不依赖复杂用户画像，只用 analytics 已有的统计字段

---

## 二、改动摘要

本轮改动集中在后端 `recommendation.py` 的三个预留方法落地，以及前端三页对新增建议类型的样式适配。**无新增 API**（复用 Round 1 的 `GET /learning/recommendations`），**无数据结构变更**（`RecommendationType` 早在 Round 1 就定义了全部四种类型）。

### 2.1 后端

1. **回补建议** `_get_review_recommendation`（`recommendation.py:473`）
   - 检测学习困难信号，推荐前置课程巩固基础
   - 带冷却机制，避免反复打扰

2. **分支建议** `_get_branch_recommendation`（`recommendation.py:644`）
   - 配置驱动，在路径分支点给出多条可选分支
   - 含通用兜底分支生成逻辑

3. **回流建议** `_get_resume_recommendation`（`recommendation.py:769`）
   - 长时间未学时，按「恢复成本」推荐最易继续的课程

4. **建议编排** `get_recommendation`（`recommendation.py:260`）
   - 建立四级优先级链路，主建议 + 备选建议组合返回

### 2.2 前端

- `Dashboard.vue` / `Learning.vue` / `LessonDetail.vue`：建议卡片新增对 `review_lesson` / `branch_path` / `resume_session` 三种类型的差异化样式（图标、配色、徽章）。
- `getRecommendationStyle()` 统一处理四种建议类型的视觉表达。

### 2.3 内容

- 13 节课程 frontmatter 中，`06-polars-joins` 与 `10-polars-lazy-pipeline` 标记为 `is_branch_point: true`，与 `BRANCH_CONFIG` 配置对应，是分支建议的真实触发点。

---

## 三、建议规则详解

### 3.1 优先级链路

`get_recommendation` 按以下顺序判定，命中即返回（主建议 + 备选）：

```
优先级 1: 回补建议（检测到学习困难）
   └─ 命中 -> 主=回补，备选=顺学（若有且不同）

优先级 2: 分支建议（刚完成分支点课程）
   └─ 命中 -> 主=分支[0]，备选=其余分支 或 顺学（去重）

优先级 3: 回流建议（长时间未学）
   └─ 命中 -> 主=回流，备选=顺学（若不同）

优先级 4: 顺学建议（默认，Round 2 已实现）
   └─ 主=顺学，无备选
```

设计意图：困难信号最优先（别让用户继续硬磕），其次是路径选择（趁热打铁给方向），再次是召回（拉回流失用户），最后才是默认推进。

### 3.2 回补建议 `_get_review_recommendation`

**触发条件**（当前课未完成时，任一满足）：

| 信号 | 阈值 | 理由模板 |
|---|---|---|
| 代码运行次数 | `code_runs >= 5`（`CODE_RUNS_THRESHOLD`） | "你在这节课尝试了 N 次代码运行，建议回顾《X》巩固基础" |
| AI 求助次数 | `ai_helps >= 3`（`AI_HELPS_THRESHOLD`） | "你请求了 N 次 AI 帮助，《X》的内容可能需要复习" |
| 代码快照数 | `snapshots >= 4`（`SNAPSHOTS_THRESHOLD`） | "你保存了 N 个代码快照但未完成，建议先回顾《X》" |
| 长时间停滞 | `code_runs>=3 且 ai_helps>=1 且 snapshots>=2`（弱信号组合，`_check_long_stall`） | "你在这节课停留了较长时间，建议先回顾《X》打好基础" |

**回补课程选择**：
1. 从当前课的 `prerequisites` 中选，优先 `is_review_friendly=true` 的前置课；
2. 无前置课时，按 `skill_tags` 在全量已完成课程中匹配 `is_review_friendly` 的课（重叠技能点最多者）；
3. 回补课本身未完成时，改用"前置知识未巩固"的特殊理由。

**冷却机制**：同一 `visitor+lesson` 触发回补后，24 小时内（`REVIEW_COOLDOWN_SECONDS`）不重复触发，避免反复打扰。冷却时间记录在内存 `_review_cooldowns` 字典（按 ISO 时间戳）。

**优先级**：5（最高），`reason_code=prerequisite_weak`，`action_label=回顾课程`。

### 3.3 分支建议 `_get_branch_recommendation`

**触发条件**：
- 当前课已完成，且 `is_branch_point=true`
- 有 `recommended_next` 且至少一个未完成

**配置驱动**（`BRANCH_CONFIG`）：

| 分支点 | 分支选项 | 高优先级条件 |
|---|---|---|
| `polars-joins` | `duckdb-sql-foundations`（SQL 对比）/ `polars-lazy-pipeline`（Polars 进阶） | 各自 prerequisites 已完成 |
| `polars-lazy-pipeline` | `polars-duckdb-workflow`（组合工作流） | polars-basics + duckdb-analytics 已完成 |

每个配置项含 `high_priority_reason` / `low_priority_reason` / `action_label` / `path_type`。前置条件全满足时 priority=4，否则 priority=3。

**通用兜底** `_get_generic_branch_recommendations`：分支点不在 `BRANCH_CONFIG` 时，直接从 `recommended_next` 生成不依赖特定技术栈的分支建议，理由文案通用化。这保证未来新增分支点无需改代码也能工作。

**返回**：分支建议列表（按 priority 降序），主建议取 `[0]`，其余作备选。

### 3.4 回流建议 `_get_resume_recommendation`

**触发条件**：
- `analytics_service` 可用
- 距上次学习 `>= 3 天`（`absence_threshold_days`，基于 `lastActiveDate`）

**候选选择 - 恢复成本模型**：

对每个「有活动但未完成」的课程计算 `resume_cost`（越低越优先）：

```
base_engagement_score = max(0, 100 - (code_runs + ai_helps*2 + snapshots*3) * 5)   # 权重 0.5
recency_score         = min(100, days_since_activity * 10)                        # 权重 0.3
difficulty_penalty    = {beginner:0, intermediate:10, advanced:30}[difficulty]    # 权重 0.2

resume_cost = base_engagement*0.5 + recency*0.3 + difficulty*0.2
```

含义：投入越多（engagement 高 -> base 低）、越近期（recency 低）、越简单（penalty 低）的课程，恢复成本越低，越值得优先继续。

**理由模板**：10 条候选模板，按数据特征**确定性选择**（非随机，保证可复现）：
- `snapshots>=3` -> 强调快照投入
- `ai_helps>=2` -> 强调 AI 求助兴趣
- `days_since_activity<=7` -> 强调记忆新鲜
- 否则 -> 通用模板

**边界处理**：
- 无未完成课但有已完成课 -> 推荐下一个顺序课程（`reason_code=long_absence`）
- 无任何完成记录 -> 推荐第一课
- 完全无活动数据 -> 返回 None

**优先级**：3，`action_label=继续学习/开始学习`。

---

## 四、修改文件列表

### 后端（1 个文件）

1. **`learn_da/app/learning/recommendation.py`**（修改）
   - `_get_review_recommendation`：从预留接口落地为完整实现（阈值判断 + 冷却 + 前置/skill_tags 匹配）
   - `_get_branch_recommendation` + `_get_generic_branch_recommendations`：配置驱动 + 通用兜底
   - `_get_resume_recommendation`：恢复成本模型 + 10 模板确定性选择
   - `get_recommendation`：四级优先级编排，主建议 + 备选组合

### 前端（3 个文件）

2. **`learn_da_vue/src/views/Dashboard.vue`**（修改）
   - `getRecommendationStyle()` 新增 `review_lesson`（橙色警示）/ `branch_path`（紫色高亮）/ `resume_session`（绿色温馨）样式分支

3. **`learn_da_vue/src/views/Learning.vue`**（修改）
   - 同上样式适配

4. **`learn_da_vue/src/views/LessonDetail.vue`**（修改）
   - 同上样式适配

> 说明：前端三页的 `getRecommendationStyle` 实现一致，按建议类型返回差异化的 containerClass/labelClass/buttonClass/badgeClass/icon/label/priorityBadge。

### 内容（13 个文件，Round 1 已落地）

- 13 节课程 frontmatter 的 `is_branch_point` 字段：`06-polars-joins`、`10-polars-lazy-pipeline` 为 `true`，其余 `false`。

---

## 五、关键设计决策

### 5.1 为什么优先级是 回补 > 分支 > 回流 > 顺学？

- **回补最优先**：用户正在卡住，继续推进只会更挫败，应先巩固基础。
- **分支次之**：用户刚完成分支点、处于决策窗口，趁热给方向价值最高。
- **回流再次**：用户已经流失，是召回动作，优先级低于当前活跃场景。
- **顺学兜底**：以上都不满足时的默认推进。

### 5.2 为什么回补建议要带冷却？

同一节课反复触发回补会让用户觉得"系统一直在说我基础差"，体验负面。24 小时冷却保证：触发一次后，即使用户继续卡，当天也不再重复推送，给用户消化空间。

冷却时间存内存（`_review_cooldowns`），服务重启会重置--可接受，因为回补本身是弱触发，重置后最多多触发一次。

### 5.3 为什么分支建议用配置驱动 + 通用兜底两层？

- `BRANCH_CONFIG` 给已有分支点（polars-joins / polars-lazy-pipeline）提供精心打磨的理由文案和前置条件判断，体验最好。
- `_get_generic_branch_recommendations` 保证未来新增分支点（比如 Python 路径的分支）即使不写配置，也能从 `recommended_next` 自动生成可用的分支建议，不会因为漏配置而静默失效。

### 5.4 为什么回流用"恢复成本"而不是简单"最近未完成"？

"最近未完成"会优先推用户最后碰的课，但那可能是难度高、投入少、早已遗忘的课，推过去反而劝退。恢复成本模型综合投入度（engagement）、时间新鲜度（recency）、难度（difficulty），倾向于推"投入多 + 记忆新 + 难度低"的课，恢复成功率更高。

### 5.5 为什么理由模板要确定性选择？

学习建议需要可复现、可调试。若用随机，同一状态每次刷新理由不同，既影响用户信任，也难排查问题。按数据特征选模板保证：相同输入 -> 相同理由。

---

## 六、与 Round 2 的兼容性

- **数据结构不变**：`RecommendationResponse` 仍是 `{primary, alternatives}`，前端 Round 2 的渲染逻辑无需改动，只是新增了类型分支样式。
- **API 不变**：仍是 `GET /learning/recommendations`，前端调用方式不变。
- **顺学建议不变**：`_get_sequential_recommendation` 逻辑与 Round 2 一致，本轮未改动。当高阶建议不触发时，自动回退到顺学建议（优先级 4）。

---

## 七、已知局限与后续方向

### 7.1 本轮局限

| 局限 | 说明 | 影响 |
|---|---|---|
| 回补冷却存内存 | 服务重启重置 | 可接受，最多多触发一次 |
| 回流阈值硬编码 3 天 | `absence_threshold_days` 不可配 | 短期可接受，后续可提为配置项 |
| 分支建议 `BRANCH_CONFIG` 仅覆盖 polars 分支点 | Python 路径无分支点配置 | 通用兜底已覆盖，体验略降但不失效 |
| 回补/回流依赖 `analytics_service` | 无 analytics 时直接返回 None | 降级合理，但无埋点环境这两类建议不可用 |

### 7.2 Round 4 方向（Agent 主导建议）

- Agent 解释推荐理由（自然语言，非模板）
- Agent 根据用户当前代码/错误生成个性化下一练习
- Agent 在多分支场景下结合用户偏好给单一推荐（而非列表）
- 建议效果埋点与回流率统计

---

## 八、验证情况

### 8.1 触发链路验证（代码静态确认）

- ✅ 回补：当前课未完成 + 阈值命中 -> 返回 `review_lesson`，priority=5
- ✅ 分支：完成 `polars-joins`（is_branch_point=true）-> `BRANCH_CONFIG` 命中 -> 返回 `branch_path` 列表
- ✅ 回流：`lastActiveDate` 距今 >=3 天 + 有未完成活动课 -> 恢复成本最低者 -> `resume_session`
- ✅ 兜底：以上均不触发 -> 顺学建议（Round 2 逻辑）

### 8.2 前端样式验证

- ✅ `getRecommendationStyle` 覆盖全部四种类型，Dashboard/Learning/LessonDetail 三页一致
- ✅ 回补=橙色警示、分支=紫色高亮、回流=绿色温馨、顺学=蓝色默认，视觉区分清晰

### 8.3 未覆盖

- ❌ 无针对 Round 3 新增建议的自动化测试（`tests/` 下无 recommendation 相关用例）
- ❌ 未在真实 analytics 数据下端到端验证回补/回流的实际触发效果

---

## 九、总结

### 9.1 本轮完成度

| 任务 | 状态 | 完成度 |
|------|------|--------|
| Task 3.1 回补建议（困难检测 + 前置课推荐 + 冷却） | ✅ 完成 | 100% |
| Task 3.2 分支建议（配置驱动 + 通用兜底） | ✅ 完成 | 100% |
| Task 3.3 回流建议（恢复成本模型 + 模板选择） | ✅ 完成 | 100% |
| 前端三页样式适配 | ✅ 完成 | 100% |
| 自动化测试 | ❌ 未做 | 0% |

### 9.2 核心价值

第三阶段建议系统至此**完整落地四类建议**：

1. **顺学**（Round 2）：正常推进时告诉你下一课
2. **回补**（Round 3）：卡住时拉你回前置课巩固
3. **分支**（Round 3）：路径分叉时给多条可选方向
4. **回流**（Round 3）：长时间未学时召回到最易继续的课

覆盖了「正常学 / 卡住 / 选方向 / 流失」四种典型学习状态，规则驱动、可解释、有冷却防打扰、有兜底防失效。为 Round 4 的 Agent 主导建议打下了完整的规则基座。

### 9.3 遗留待办

- [ ] 补充 recommendation 服务的单元测试（回补阈值/冷却、分支配置、回流成本模型）
- [ ] 将 `absence_threshold_days` 等阈值提为可配置项
- [ ] 真实数据下端到端验证回补/回流触发效果
- [ ] 启动 Round 4：Agent 主导建议

---

**文档版本**: v1.0（事后补齐，对齐 main 当前实现）
**最后更新**: 2026-07-09
