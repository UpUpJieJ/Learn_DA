# Phase 3 Round 2 改动清单

## 修改文件 (4个)

### 后端 (1个)
- `learn_da/app/learning/recommendation.py` - 完善顺学建议规则

### 前端 (3个)
- `learn_da_vue/src/views/Dashboard.vue` - 接入下一步建议卡片
- `learn_da_vue/src/views/Learning.vue` - 接入继续学习入口
- `learn_da_vue/src/views/LessonDetail.vue` - 接入学后建议区块

## 核心改动

### 1. 顺学建议规则优化

```python
# 新增逻辑：当前课未完成时不推荐新课
if current_lesson_slug in completed_lessons:
    # 已完成，推荐后继
    return recommendation
else:
    # 未完成，返回 None
    return None
```

### 2. 三个页面接入建议

**Dashboard**: 概览区块增加建议卡片  
**Learning**: 路径介绍后增加建议区块  
**LessonDetail**: 正文底部增加学后建议  

### 3. 兜底策略

- Dashboard: 新建议 → 旧推荐 → 不显示
- Learning: 新建议 → 继续学习 → 不显示
- LessonDetail: 新建议 → 不显示

## 验证结果

✅ 新用户 → polars-basics  
✅ 完成第一课 → duckdb-analytics  
✅ 当前课未完成 → None (正确)  
✅ 完成多门课程 → 顺序推进  
✅ 三个页面正确展示建议  
✅ 兜底策略正常工作  

## 下一步

Phase 3 Round 3:
- 定义"卡住"的最小规则
- 实现回补课推荐
- 展示推荐理由
- 验证回补效果
