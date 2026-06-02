---
id: 10
slug: polars-lazy-pipeline
title: Polars 惰性流水线
category: polars
difficulty: intermediate
estimated_minutes: 35
order: 10
tags: [polars, lazy, pipeline, query optimization, performance]
prev_lesson:
  slug: duckdb-window-functions
  title: DuckDB 窗口函数
next_lesson:
  slug: polars-duckdb-workflow
  title: Polars 与 DuckDB 组合工作流
practice_objective: >-
  理解 Polars 的 eager 和 lazy 两种执行模式，
  能用 lazy() + collect() 构建可优化的分析流水线。
completion_criteria:
  - 用 .lazy() 将 DataFrame 转为惰性模式
  - 在惰性模式下链式调用 filter、with_columns、group_by
  - 用 .collect() 触发实际计算
  - 理解惰性模式为什么更适合复杂分析
# Phase 3: 建议系统元数据
track: polars_advanced
prerequisites: [polars-basics, polars-groupby, polars-expressions]
recommended_next: [polars-duckdb-workflow]
skill_tags: [lazy_evaluation, query_optimization, pipeline, performance]
is_review_friendly: false
is_branch_point: true
---

# Polars 惰性流水线

## Eager vs Lazy

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| Eager（默认） | 每一步立即执行并返回结果 | 快速查看数据、简单操作 |
| Lazy | 先描述计算计划，`collect()` 时才执行 | 多步分析、大数据、需要优化 |

一句话：Eager 是"说一步做一步"，Lazy 是"把计划说完再一起做"。

## 核心概念

Polars 默认可以立即执行，也可以进入惰性模式。惰性模式下，代码先描述计算计划，直到调用 `collect()` 才真正执行。

惰性模式的好处：

- **查询优化**：Polars 会自动合并过滤、选择等步骤，减少中间数据
- **内存友好**：不需要每步都生成完整 DataFrame
- **链式写法**：复杂分析可以写成一条清晰的流水线

## 构建惰性分析流程

```python
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5],
    "region": ["华东", "华东", "华南", "华南", "华北"],
    "category": ["办公", "数码", "办公", "配件", "办公"],
    "amount": [120, 899, 240, 59, 180],
})

# 进入惰性模式
query = (
    orders.lazy()
    .filter(pl.col("amount") >= 100)
    .with_columns(
        pl.when(pl.col("amount") >= 500)
        .then(pl.lit("大额"))
        .otherwise(pl.lit("普通"))
        .alias("amount_band")
    )
    .group_by(["region", "amount_band"])
    .agg(
        pl.len().alias("order_count"),
        pl.col("amount").sum().alias("total_amount"),
    )
    .sort("total_amount", descending=True)
)

# 此时还没有执行任何计算
print(type(query))  # LazyFrame

# collect() 触发实际计算
result = query.collect()
print(result)
```

## 什么时候使用 lazy

| 场景 | 建议 |
|------|------|
| 查看前几行、简单筛选 | 用 Eager（默认） |
| 3 步以上的分析流水线 | 用 Lazy |
| 读取大文件 + 多步处理 | 用 Lazy（优化后更省内存） |
| 需要链式写法表达分析逻辑 | 用 Lazy |

## 练习

把以下 Eager 写法改写成 Lazy 流水线，完成 4 个动作：

```python
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5, 6],
    "region": ["华东", "华东", "华南", "华南", "华北", "华北"],
    "category": ["办公", "数码", "办公", "配件", "办公", "数码"],
    "amount": [120, 899, 240, 59, 180, 620],
})
```

**动作 1**：用 `.lazy()` 转换为惰性模式，然后过滤掉金额小于 100 的订单，最后 `.collect()` 查看结果。

**动作 2**：在动作 1 的基础上，添加一个 `amount_band` 列（≥500 为"大额"，其余为"普通"）。

**动作 3**：继续链式调用，按 `region` 和 `amount_band` 分组，统计订单数和总金额。

**动作 4**：把整条流水线写成一个变量 `pipeline`，分步查看：先 `print(pipeline.explain())` 查看执行计划，再 `print(pipeline.collect())` 查看结果。

```python:example
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5, 6],
    "region": ["华东", "华东", "华南", "华南", "华北", "华北"],
    "category": ["办公", "数码", "办公", "配件", "办公", "数码"],
    "amount": [120, 899, 240, 59, 180, 620],
})

pipeline = (
    orders.lazy()
    .filter(pl.col("amount") >= 100)
    .with_columns(
        pl.when(pl.col("amount") >= 500)
        .then(pl.lit("大额"))
        .otherwise(pl.lit("普通"))
        .alias("amount_band")
    )
    .group_by(["region", "amount_band"])
    .agg(
        pl.len().alias("order_count"),
        pl.col("amount").sum().alias("total_amount"),
    )
    .sort("total_amount", descending=True)
)

# 查看执行计划（可选）
print(pipeline.explain())

# 执行
result = pipeline.collect()
print(result)
```

## 常见错误

**错误 1：在 LazyFrame 上直接 print**
```python
# 这不会报错，但也不会执行计算
query = orders.lazy().filter(pl.col("amount") > 100)
print(query)  # 打印的是 LazyFrame 对象，不是数据

# 正确：collect() 后再 print
print(query.collect())
```

**错误 2：忘记 collect()**
```python
# 错误：result 是 LazyFrame，不是 DataFrame
result = orders.lazy().filter(...)
result.write_csv("out.csv")  # 可能报错或行为异常

# 正确：先 collect
result = orders.lazy().filter(...).collect()
result.write_csv("out.csv")
```

**错误 3：在 lazy 链中混用 eager 操作**
```python
# 错误：.head() 在 lazy 模式下行为不同
orders.lazy().filter(...).head(10)  # head 在 lazy 中是可选的

# 建议：整个流水线保持 lazy，最后 collect()
orders.lazy().filter(...).collect().head(10)
```

## 下一步建议

完成本课后，建议继续：
- **Polars 与 DuckDB 组合工作流**：学习 Polars 清洗 + DuckDB SQL 分析的组合模式
- 在 Playground 中尝试用 `pipeline.explain()` 查看执行计划，理解 Polars 的优化策略
