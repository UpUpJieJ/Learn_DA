---
id: 4
slug: polars-expressions
title: Polars 表达式与列计算
category: polars
difficulty: beginner
estimated_minutes: 25
order: 4
tags: [polars, expression, with_columns, 列计算]
prev_lesson:
  slug: polars-groupby
  title: Polars 分组聚合
next_lesson:
  slug: polars-cleaning
  title: Polars 数据清洗
---

# Polars 表达式与列计算

## 学习目标

- 理解 Polars 中表达式的作用
- 使用 `with_columns` 创建派生列
- 用条件表达式完成简单业务分层

## 核心概念

Polars 的多数计算都通过表达式完成。表达式不会马上取出某一列的值，而是描述"要怎样计算"。常见入口包括：

- `pl.col("列名")`：引用列
- `pl.lit(值)`：创建字面量
- `alias("新列名")`：给计算结果命名
- `pl.when(...).then(...).otherwise(...)`：条件分支

这种写法让多列计算可以一次提交给 Polars 执行，便于优化和并行处理。

## 创建派生指标

```python
import polars as pl

df = pl.DataFrame({
    "product": ["键盘", "鼠标", "显示器", "耳机"],
    "price": [199, 89, 1299, 299],
    "quantity": [5, 12, 2, 7],
})

result = df.with_columns(
    (pl.col("price") * pl.col("quantity")).alias("revenue"),
    (pl.col("price") >= 300).alias("is_high_price"),
)

print(result)
```

## 条件分层

```python
result = result.with_columns(
    pl.when(pl.col("revenue") >= 1000)
    .then(pl.lit("重点关注"))
    .when(pl.col("revenue") >= 500)
    .then(pl.lit("正常跟进"))
    .otherwise(pl.lit("观察"))
    .alias("action")
)
```

## 练习建议

使用一张商品销售表，尝试完成以下任务：

- 新增 `discount_price`，表示 9 折后的价格
- 新增 `gross_profit`，表示收入减去成本
- 按收入把商品分为"高收入"、"中收入"、"低收入"

```python:example
import polars as pl

df = pl.DataFrame({
    "product": ["键盘", "鼠标", "显示器", "耳机"],
    "price": [199, 89, 1299, 299],
    "quantity": [5, 12, 2, 7],
})

result = df.with_columns(
    (pl.col("price") * pl.col("quantity")).alias("revenue"),
    pl.when(pl.col("price") >= 300)
    .then(pl.lit("高客单"))
    .otherwise(pl.lit("普通"))
    .alias("price_band"),
)

print(result)
```
