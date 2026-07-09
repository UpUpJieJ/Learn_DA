# Learn DA 第三阶段第一轮实现总结

**实施时间**: 2026-05-31  
**实施范围**: 阶段 1 - 建立课程建议规则骨架  
**对应任务**: Task 1.1, 1.2, 1.3

---

## 一、实施目标

本轮目标是为 Learn DA 第三阶段"下一步学习建议系统"搭建稳定骨架，为后续顺学建议、回补建议、分支建议做基础，但**不追求全部规则落地**。

核心原则：
- ✅ 建立课程元数据体系
- ✅ 定义统一建议数据结构
- ✅ 创建可扩展的建议服务骨架
- ❌ 不做黑盒推荐
- ❌ 不做 Agent 主导推荐
- ❌ 不做复杂用户画像
- ❌ 不做大规模页面重构

---

## 二、改动摘要

### 2.1 核心改动

1. **新增建议服务模块** (`learn_da/app/learning/recommendation.py`)
   - 定义了建议类型、理由代码、建议数据结构
   - 实现了 `RecommendationService` 统一入口
   - 实现了基础顺学建议逻辑
   - 预留了回补、分支、回流建议接口

2. **扩展课程元数据** (11 个课程 Markdown 文件)
   - 为所有课程添加了 Phase 3 元数据字段
   - 包括：track, prerequisites, recommended_next, skill_tags, is_review_friendly, is_branch_point

3. **更新数据结构定义**
   - 后端：`learn_da/app/learning/schemas.py` 新增建议相关 schema
   - 前端：`learn_da_vue/src/types/api.ts` 新增建议类型定义

4. **新增 API 接口**
   - `GET /learning/recommendations` - 获取用户学习建议
   - 前端 API 封装：`learn_da_vue/src/api/recommendation.ts`

5. **更新内容加载器**
   - `learn_da/app/core/content_loader.py` 支持解析新增元数据字段

---

## 三、修改文件列表

### 后端文件 (6 个)

1. **learn_da/app/learning/recommendation.py** (新增)
   - 建议服务核心逻辑
   - 课程元数据管理
   - 顺学建议规则实现

2. **learn_da/app/learning/schemas.py** (修改)
   - 新增 `LearningRecommendation` schema
   - 新增 `RecommendationResponse` schema

3. **learn_da/app/learning/router.py** (修改)
   - 新增 `/recommendations` 接口
   - 新增 `get_recommendation_service` 依赖注入

4. **learn_da/app/core/content_loader.py** (修改)
   - 扩展 `load_lesson_from_file` 解析新字段

5. **learn_da/test_recommendation.py** (新增)
   - 建议服务测试脚本

### 前端文件 (2 个)

6. **learn_da_vue/src/types/api.ts** (修改)
   - 新增 `RecommendationType` 类型
   - 新增 `RecommendationReasonCode` 类型
   - 新增 `LearningRecommendation` 接口
   - 新增 `RecommendationResponse` 接口

7. **learn_da_vue/src/api/recommendation.ts** (新增)
   - `getRecommendations` API 封装

### 课程内容文件 (11 个)

8-18. **content/lessons/*.md** (全部修改)
   - 01-polars-basics.md
   - 02-duckdb-analytics.md
   - 03-polars-groupby.md
   - 04-polars-expressions.md
   - 05-polars-cleaning.md
   - 06-polars-joins.md
   - 07-duckdb-sql-foundations.md
   - 08-duckdb-joins-cte.md
   - 09-duckdb-window-functions.md
   - 10-polars-lazy-pipeline.md
   - 11-polars-duckdb-workflow.md

---

## 四、课程元数据最终组织方式

### 4.1 元数据字段设计

每门课程的 frontmatter 现在包含以下 Phase 3 字段：

```yaml
# Phase 3: 建议系统元数据
track: polars_basics                    # 所属路径
prerequisites: [polars-basics]          # 前置课程 slug 列表
recommended_next: [polars-groupby]      # 推荐后继课程 slug 列表
skill_tags: [dataframe, select, filter] # 技能点标签
is_review_friendly: true                # 是否适合作为回补课
is_branch_point: false                  # 是否是路径分支点
```

### 4.2 路径 (Track) 分类

系统定义了 5 个学习路径：

| Track | 课程数 | 说明 |
|-------|--------|------|
| `polars_basics` | 5 | Polars 基础路径 (01-06) |
| `polars_advanced` | 1 | Polars 进阶路径 (10) |
| `duckdb_basics` | 2 | DuckDB 基础路径 (02, 07) |
| `duckdb_advanced` | 2 | DuckDB 进阶路径 (08-09) |
| `combined_workflow` | 1 | 组合实战路径 (11) |

### 4.3 元数据统计

- **总课程数**: 11
- **有前置课程的**: 10 (91%)
- **有推荐后继的**: 10 (91%)
- **适合回补的**: 5 (45%) - 主要是 beginner 难度和基础课
- **分支点**: 2 (18%) - polars-joins, polars-lazy-pipeline

### 4.4 元数据推断规则

为了兼容未完整填写元数据的课程，系统实现了智能推断：

1. **track 推断**：根据 category 和 slug 关键词推断
2. **prerequisites 推断**：从 prev_lesson 字段提取
3. **recommended_next 推断**：从 next_lesson 字段提取
4. **is_review_friendly 推断**：beginner 难度或包含 "basics"/"foundations" 关键词

---

## 五、建议结果数据结构

### 5.1 建议类型 (RecommendationType)

```typescript
type RecommendationType =
  | "next_lesson"      // 顺学建议：继续下一课
  | "review_lesson"    // 回补建议：回看前置课
  | "branch_path"      // 分支建议：切换学习路径
  | "resume_session";  // 回流建议：恢复中断的学习
```

### 5.2 理由代码 (RecommendationReasonCode)

```typescript
type RecommendationReasonCode =
  | "sequential_progress"   // 顺序推进
  | "prerequisite_weak"     // 前置知识薄弱
  | "stuck_on_practice"     // 练习卡住
  | "path_completed"        // 路径完成
  | "long_absence"          // 长时间未学习
  | "incomplete_practice";  // 未完成的练习
```

### 5.3 建议数据结构

```typescript
interface LearningRecommendation {
  type: RecommendationType;           // 建议类型
  targetSlug: string;                 // 目标课程 slug
  targetTitle: string;                // 目标课程标题
  reason: string;                     // 推荐理由（用户可读）
  reasonCode: RecommendationReasonCode; // 理由代码（前端逻辑判断）
  priority: number;                   // 优先级 (1-5)
  actionLabel: string;                // 行动按钮文案
  context?: Record<string, unknown>;  // 额外上下文（可选）
}

interface RecommendationResponse {
  primary: LearningRecommendation | null;      // 主要建议
  alternatives: LearningRecommendation[];      // 备选建议
}
```

---

## 六、建议服务骨架设计

### 6.1 服务位置

**位置**: `learn_da/app/learning/recommendation.py`

**原因**:
- 建议逻辑与课程内容紧密相关，放在 `learning` 模块下语义清晰
- 与 `learning/service.py` 并列，职责分离
- 避免散落在多个页面或 analytics 模块中

### 6.2 核心架构

```python
class RecommendationService:
    """学习建议服务"""
    
    def __init__(self, repository):
        self.repository = repository
        self._lesson_metadata_cache = None
    
    # 统一入口
    async def get_recommendation(
        visitor_id, completed_lessons, current_lesson_slug
    ) -> RecommendationResponse
    
    # 元数据管理
    def _get_lesson_metadata() -> dict[str, LessonMetadata]
    def _infer_track(lesson) -> str
    
    # 规则实现（本轮只实现了顺学）
    def _get_sequential_recommendation() -> LearningRecommendation
    def _get_review_recommendation() -> LearningRecommendation  # 预留
    def _get_branch_recommendation() -> list[LearningRecommendation]  # 预留
    def _get_resume_recommendation() -> LearningRecommendation  # 预留
```

### 6.3 设计优势

1. **统一入口**: 所有建议请求通过 `get_recommendation` 统一处理
2. **可扩展**: 预留了 4 类建议规则的接口，后续轮次逐步实现
3. **元数据缓存**: 课程元数据只加载一次，提升性能
4. **规则分离**: 不同类型建议逻辑独立，便于维护和测试
5. **不污染页面层**: 页面只需调用 API，不关心规则细节

---

## 七、本轮实现的规则

### 7.1 顺学建议规则 (已实现)

**触发条件**: 默认推荐逻辑

**规则逻辑**:
1. 如果当前有课程，推荐其 `recommended_next` 中的第一个未完成课程
2. 否则找第一个未完成的课程（按 order 排序）
3. 如果全部完成，返回 None

**测试结果**:
- ✅ 新用户 → 推荐 `polars-basics`
- ✅ 完成 `polars-basics` → 推荐 `duckdb-analytics`
- ✅ 完成 `polars-joins` (分支点) → 推荐 `duckdb-sql-foundations`

### 7.2 刻意留到下一轮的规则

以下规则已预留接口，但**本轮不实现**：

1. **回补建议** (`_get_review_recommendation`)
   - 触发条件：同一课多次失败、多次求助、长时间停滞
   - 需要：analytics 数据支持（code_runs, ai_helps, snapshots）
   - 计划：Phase 3 Round 2 实现

2. **分支建议** (`_get_branch_recommendation`)
   - 触发条件：完成某阶段后的路径分流点
   - 需要：用户路径偏好分析
   - 计划：Phase 3 Round 3 实现

3. **回流建议** (`_get_resume_recommendation`)
   - 触发条件：长时间未学习后回来
   - 需要：last_active_date 分析
   - 计划：Phase 3 Round 3 实现

---

## 八、验证结果

### 8.1 元数据加载验证

```
✓ 加载了 11 门课程
✓ 所有课程都有 track 字段
✓ 10/11 课程有 prerequisites
✓ 10/11 课程有 recommended_next
✓ 5/11 课程标记为 review_friendly
✓ 2/11 课程标记为 branch_point
```

### 8.2 建议服务验证

```
✓ 场景1: 新用户 → polars-basics (priority: 2)
✓ 场景2: 完成第一课 → duckdb-analytics (priority: 3)
✓ 场景3: 完成多门课程 → polars-groupby (priority: 3)
✓ 元数据缓存正常工作
✓ 推断规则正常工作
```

### 8.3 API 接口验证

- ✅ 路由注册成功
- ✅ 依赖注入正常
- ✅ Schema 序列化正常
- ⚠️ 需要启动服务后进行端到端测试

---

## 九、下一轮工作方向

### 9.1 Phase 3 Round 2 建议内容

**目标**: 跑通默认顺学建议 + 回补建议

**任务**:
1. 把建议接入 Dashboard / Learning / LessonDetail 页面
2. 实现回补建议规则（基于 analytics 数据）
3. 展示推荐理由
4. 用户可见效果验证

### 9.2 Phase 3 Round 3 建议内容

**目标**: 分支建议 + 回流建议

**任务**:
1. 实现分支建议规则
2. 实现回流建议规则
3. 完善备选建议逻辑
4. 建议系统完整性验证

---

## 十、关键决策记录

### 10.1 为什么不在本轮做页面展示？

**原因**:
- 本轮重点是"规则输入 + 统一数据结构 + 单一服务入口"
- 页面展示需要设计交互、调整布局，容易扩散范围
- 先确保后端骨架稳定，再做前端集成更高效

**下一轮计划**:
- Dashboard 增加"下一步学习建议"区块
- Learning 页增加"继续学习"入口
- LessonDetail 页底部增加"学完后的建议"

### 10.2 为什么元数据放在 Markdown frontmatter？

**原因**:
- 课程内容和元数据在同一文件，维护成本低
- 不需要额外的数据库表或配置文件
- 支持版本控制，便于审查和回滚
- 与现有 Phase 2 字段保持一致

**缺点**:
- 元数据修改需要重启服务（可接受，课程不频繁变动）
- 不支持动态调整（本阶段不需要）

### 10.3 为什么建议服务不依赖 analytics 数据？

**本轮设计**:
- 顺学建议只依赖课程元数据和完成列表
- 不需要查询数据库，性能更好
- 规则更简单、更可控

**后续扩展**:
- Round 2 回补建议会引入 analytics 数据
- 通过依赖注入传入 analytics service
- 保持服务接口不变

---

## 十一、总结

### 11.1 本轮完成度

| 任务 | 状态 | 完成度 |
|------|------|--------|
| Task 1.1 盘点并整理课程元数据 | ✅ 完成 | 100% |
| Task 1.2 定义建议结果的数据结构 | ✅ 完成 | 100% |
| Task 1.3 建立建议规则服务骨架 | ✅ 完成 | 100% |

### 11.2 交付物清单

- ✅ 11 门课程的完整元数据
- ✅ 统一的建议数据结构（前后端一致）
- ✅ 可扩展的建议服务骨架
- ✅ 基础顺学建议规则实现
- ✅ API 接口和前端封装
- ✅ 测试脚本和验证结果

### 11.3 核心价值

本轮实现为 Learn DA 第三阶段建立了**稳定、可扩展、可维护**的建议系统基础：

1. **稳定**: 数据结构清晰，接口定义明确
2. **可扩展**: 预留了 4 类建议规则接口，后续轮次逐步实现
3. **可维护**: 规则逻辑集中在单一服务，不散落在多个页面

这是一个**规则驱动、可解释、可审查**的建议系统骨架，而不是黑盒推荐系统。

---

**实施人**: Claude (Sonnet 4.6)  
**文档版本**: v1.0  
**最后更新**: 2026-05-31
