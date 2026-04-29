---
id: 11
slug: polars-duckdb-workflow
title: Polars 与 DuckDB 组合工作流
category: combined
difficulty: advanced
estimated_minutes: 45
order: 11
tags: [polars, duckdb, workflow, 实战]
prev_lesson:
  slug: polars-lazy-pipeline
  title: Polars 惰性流水线
---

# Polars 与 DuckDB 组合工作流

## 学习目标

- 理解 Polars 和 DuckDB 在分析流程中的分工
- 用 Polars 完成清洗和派生列
- 用 DuckDB SQL 完成汇总和排名

## 核心概念

Polars 和 DuckDB 都能做很多数据分析任务，但它们的表达方式不同：

- Polars 适合用表达式构建可组合的数据处理流水线
- DuckDB 适合用 SQL 快速表达连接、聚合、窗口函数
- 组合使用时，可以先用 Polars 清洗数据，再把结果注册到 DuckDB 中做 SQL 分析

## 从清洗到 SQL 分析

```python
import duckdb
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5, 6],
    "region": ["华东", "华东", "华南", "华南", "华北", None],
    "category": ["办公", "数码", "办公", "配件", "办公", "数码"],
    "amount": [120, 899, 240, 59, 180, 620],
})

clean_orders = orders.with_columns(
    pl.col("region").fill_null("未知"),
    pl.when(pl.col("amount") >= 500)
    .then(pl.lit("大额"))
    .otherwise(pl.lit("普通"))
    .alias("amount_band"),
)

con = duckdb.connect()
con.register("orders", clean_orders.to_arrow())

result = con.execute("""
    WITH region_summary AS (
        SELECT
            region,
            amount_band,
            COUNT(*) AS order_count,
            SUM(amount) AS total_amount
        FROM orders
        GROUP BY region, amount_band
    )
    SELECT
        region,
        amount_band,
        order_count,
        total_amount,
        RANK() OVER (ORDER BY total_amount DESC) AS amount_rank
    FROM region_summary
    ORDER BY amount_rank
""").fetchall()

print(result)
```

## 工作流建议

一个清晰的组合流程通常包括：

- 数据进入 Polars，先统一类型、处理缺失值
- 用 Polars 表达式生成业务字段
- 将处理后的表注册给 DuckDB
- 用 SQL 写汇总、排名、分层分析
- 回到 Polars 或 Python 中继续展示结果

## 练习建议

设计一个小型销售分析项目：

- 构造订单表和商品表
- 用 Polars 补充金额字段、处理缺失区域
- 把清洗后的数据注册到 DuckDB
- 用 SQL 找出销售额最高的区域和品类

```python:example
import duckdb
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5, 6],
    "region": ["华东", "华东", "华南", "华南", "华北", None],
    "category": ["办公", "数码", "办公", "配件", "办公", "数码"],
    "amount": [120, 899, 240, 59, 180, 620],
})

clean_orders = orders.with_columns(
    pl.col("region").fill_null("未知"),
    pl.when(pl.col("amount") >= 500)
    .then(pl.lit("大额"))
    .otherwise(pl.lit("普通"))
    .alias("amount_band"),
)

con = duckdb.connect()
con.register("orders", clean_orders.to_arrow())

result = con.execute("""
    SELECT region, SUM(amount) AS total_amount
    FROM orders
    GROUP BY region
    ORDER BY total_amount DESC
""").fetchall()

print(result)
```
