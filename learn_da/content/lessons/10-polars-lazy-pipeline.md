---
id: 10
slug: polars-lazy-pipeline
title: Polars 惰性流水线
category: polars
difficulty: intermediate
estimated_minutes: 35
order: 10
tags: [polars, lazy, pipeline, query optimization]
prev_lesson:
  slug: duckdb-window-functions
  title: DuckDB 窗口函数
next_lesson:
  slug: polars-duckdb-workflow
  title: Polars 与 DuckDB 组合工作流
---

# Polars 惰性流水线

## 学习目标

- 区分 eager 和 lazy 两种执行方式
- 使用 `lazy()`、`collect()` 构建分析流水线
- 理解惰性执行为什么更适合复杂分析

## 核心概念

Polars 默认可以立即执行，也可以进入惰性模式。惰性模式下，代码先描述计算计划，直到调用 `collect()` 才真正执行。

惰性模式的好处：

- 可以把过滤、选择、聚合合并优化
- 更适合处理大数据文件
- 复杂步骤可以用链式写法表达成一条流水线

## 构建惰性分析流程

```python
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5],
    "region": ["华东", "华东", "华南", "华南", "华北"],
    "category": ["办公", "数码", "办公", "配件", "办公"],
    "amount": [120, 899, 240, 59, 180],
})

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

result = query.collect()
print(result)
```

## 什么时候使用 lazy

如果只是查看几行数据，直接使用 DataFrame 很方便。如果分析包含多步过滤、派生列、连接和聚合，推荐用 lazy 把流程组织起来。

## 练习建议

把之前课程中的订单分析改写成 lazy 流水线：

- 先过滤掉金额小于 100 的订单
- 添加金额分层字段
- 按区域和分层统计订单数、总金额
- 最后调用 `collect()` 得到结果

```python:example
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5],
    "region": ["华东", "华东", "华南", "华南", "华北"],
    "category": ["办公", "数码", "办公", "配件", "办公"],
    "amount": [120, 899, 240, 59, 180],
})

result = (
    orders.lazy()
    .filter(pl.col("amount") >= 100)
    .group_by("region")
    .agg(pl.col("amount").sum().alias("total_amount"))
    .sort("total_amount", descending=True)
    .collect()
)

print(result)
```
