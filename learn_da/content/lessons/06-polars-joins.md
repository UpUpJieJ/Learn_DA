---
id: 6
slug: polars-joins
title: Polars 连接与合并
category: polars
difficulty: intermediate
estimated_minutes: 30
order: 6
tags: [polars, join, lookup, 数据建模]
prev_lesson:
  slug: polars-cleaning
  title: Polars 数据清洗
next_lesson:
  slug: duckdb-sql-foundations
  title: DuckDB SQL 分析基础
---

# Polars 连接与合并

## 学习目标

- 理解事实表与维度表的基本关系
- 使用 `join` 补充字段
- 选择适合场景的连接类型

## 核心概念

数据分析中经常把多张表合并。例如订单表记录交易，商品表记录品类和成本。连接可以把分散的信息组织成一张分析宽表。

常见连接类型：

- `left`：保留左表所有记录，适合给事实表补充信息
- `inner`：只保留两边都匹配的记录
- `outer`：保留两边所有记录
- `semi`：保留左表中能匹配右表的记录
- `anti`：保留左表中不能匹配右表的记录

## 连接商品维表

```python
import polars as pl

orders = pl.DataFrame({
    "order_id": [101, 102, 103, 104],
    "product_id": [1, 2, 1, 3],
    "quantity": [2, 1, 5, 3],
})

products = pl.DataFrame({
    "product_id": [1, 2, 3],
    "category": ["办公", "数码", "配件"],
    "unit_price": [120, 899, 59],
})

joined = orders.join(products, on="product_id", how="left")
result = joined.with_columns(
    (pl.col("quantity") * pl.col("unit_price")).alias("amount")
)

print(result)
```

## 找出未匹配记录

```python
unknown_orders = orders.join(products, on="product_id", how="anti")
```

`anti` 连接很适合做数据质量检查：订单里是否出现了商品维表不存在的商品编号。

## 练习建议

创建用户表和订单表，完成以下分析：

- 用 `left join` 给订单补充用户城市
- 按城市统计订单金额
- 用 `anti join` 找出没有用户信息的订单

```python:example
import polars as pl

orders = pl.DataFrame({
    "order_id": [101, 102, 103, 104],
    "product_id": [1, 2, 1, 3],
    "quantity": [2, 1, 5, 3],
})

products = pl.DataFrame({
    "product_id": [1, 2, 3],
    "category": ["办公", "数码", "配件"],
    "unit_price": [120, 899, 59],
})

result = (
    orders.join(products, on="product_id", how="left")
    .with_columns((pl.col("quantity") * pl.col("unit_price")).alias("amount"))
    .group_by("category")
    .agg(pl.col("amount").sum().alias("total_amount"))
    .sort("total_amount", descending=True)
)

print(result)
```
