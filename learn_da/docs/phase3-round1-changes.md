# Phase 3 Round 1 改动清单

## 新增文件 (3个)

1. `learn_da/app/learning/recommendation.py` - 建议服务核心模块
2. `learn_da_vue/src/api/recommendation.ts` - 前端 API 封装
3. `docs/phase3-round1-completion-summary.md` - 实施总结文档

## 修改文件 (15个)

### 后端 (3个)
- `learn_da/app/learning/schemas.py` - 新增建议相关 schema
- `learn_da/app/learning/router.py` - 新增 /recommendations 接口
- `learn_da/app/core/content_loader.py` - 支持解析新元数据字段

### 前端 (1个)
- `learn_da_vue/src/types/api.ts` - 新增建议类型定义

### 课程内容 (11个)
- `content/lessons/01-polars-basics.md`
- `content/lessons/02-duckdb-analytics.md`
- `content/lessons/03-polars-groupby.md`
- `content/lessons/04-polars-expressions.md`
- `content/lessons/05-polars-cleaning.md`
- `content/lessons/06-polars-joins.md`
- `content/lessons/07-duckdb-sql-foundations.md`
- `content/lessons/08-duckdb-joins-cte.md`
- `content/lessons/09-duckdb-window-functions.md`
- `content/lessons/10-polars-lazy-pipeline.md`
- `content/lessons/11-polars-duckdb-workflow.md`

## 核心改动说明

### 1. 课程元数据扩展

每门课程新增 Phase 3 字段：
```yaml
track: polars_basics
prerequisites: [polars-basics]
recommended_next: [polars-groupby]
skill_tags: [dataframe, select, filter]
is_review_friendly: true
is_branch_point: false
```

### 2. 建议数据结构

```typescript
interface LearningRecommendation {
  type: "next_lesson" | "review_lesson" | "branch_path" | "resume_session";
  targetSlug: string;
  targetTitle: string;
  reason: string;
  reasonCode: string;
  priority: number;
  actionLabel: string;
}
```

### 3. API 接口

```
GET /learning/recommendations
  ?visitor_id=xxx
  &completed_lessons=slug1,slug2
  &current_lesson=slug3
```

## 验证结果

✅ 元数据加载: 11门课程全部成功  
✅ 建议服务: 3个测试场景全部通过  
✅ 数据结构: 前后端类型定义一致  
✅ API 路由: 注册成功，依赖注入正常  

## 下一步

Phase 3 Round 2:
- 接入 Dashboard / Learning / LessonDetail 页面
- 实现回补建议规则
- 展示推荐理由
