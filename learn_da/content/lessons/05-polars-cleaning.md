---
id: 5
slug: polars-cleaning
title: Polars 数据清洗
category: polars
difficulty: beginner
estimated_minutes: 30
order: 5
tags: [polars, cleaning, missing-values, 数据清洗]
prev_lesson:
  slug: polars-expressions
  title: Polars 表达式与列计算
next_lesson:
  slug: polars-joins
  title: Polars 连接与合并
---

# Polars 数据清洗

## 学习目标

- 识别空值、重复值和类型问题
- 使用 `drop_nulls`、`fill_null`、`unique` 清理数据
- 在清洗后保留可解释的数据处理步骤

## 核心概念

真实数据经常存在缺失、重复、格式不一致等问题。清洗时要先明确规则，再把规则写成可复现的代码。

常用方法包括：

- `null_count()`：查看每列缺失数量
- `fill_null()`：用固定值或统计值填充空值
- `drop_nulls()`：删除包含空值的记录
- `unique()`：去重
- `cast()`：转换字段类型

## 缺失值处理

```python
import polars as pl

df = pl.DataFrame({
    "user_id": [1, 2, 2, 3, 4],
    "city": ["北京", None, None, "上海", "深圳"],
    "score": [88, None, None, 95, 76],
})

print(df.null_count())

cleaned = (
    df.unique(subset=["user_id"], keep="first")
    .with_columns(
        pl.col("city").fill_null("未知").alias("city"),
        pl.col("score").fill_null(pl.col("score").mean()).alias("score"),
    )
)

print(cleaned)
```

## 类型转换

如果日期或金额以字符串形式进入系统，分析前应转成合适类型：

```python
orders = pl.DataFrame({
    "order_date": ["2026-01-01", "2026-01-02"],
    "amount": ["100.5", "86.0"],
})

orders = orders.with_columns(
    pl.col("order_date").str.to_date("%Y-%m-%d"),
    pl.col("amount").cast(pl.Float64),
)
```

## 练习建议

构造一张用户表，加入重复用户、缺失城市、字符串金额，然后完成：

- 查看每列缺失数量
- 对城市填充"未知"
- 删除重复用户
- 把金额转换为浮点数

```python:example
import polars as pl

df = pl.DataFrame({
    "user_id": [1, 2, 2, 3, 4],
    "city": ["北京", None, None, "上海", "深圳"],
    "score": [88, None, None, 95, 76],
})

cleaned = (
    df.unique(subset=["user_id"], keep="first")
    .with_columns(
        pl.col("city").fill_null("未知"),
        pl.col("score").fill_null(pl.col("score").mean()),
    )
)

print(cleaned.sort("user_id"))
```
