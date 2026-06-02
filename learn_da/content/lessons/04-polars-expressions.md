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
practice_objective: >-
  掌握 Polars 表达式的核心写法，能用 with_columns 完成列计算、
  用 pl.when().then().otherwise() 完成条件分层。
completion_criteria:
  - 用 with_columns + 算术表达式创建派生列
  - 用 pl.when().then().otherwise() 做条件分层
  - 用 alias() 给新列命名
  - 用 pl.lit() 插入常量值
# Phase 3: 建议系统元数据
track: polars_basics
prerequisites: ['polars-basics', 'polars-groupby']
recommended_next: ['polars-cleaning']
skill_tags: ['expressions', 'with_columns', 'conditional_logic', 'pl_when']
is_review_friendly: true
is_branch_point: false
---

# Polars 表达式与列计算

## Pandas → Polars 对照

| Pandas | Polars | 说明 |
|--------|--------|------|
| `df['a'] * df['b']` | `pl.col('a') * pl.col('b')` | Polars 用 `pl.col()` 引用列 |
| `df.assign(y = df.x * 2)` | `df.with_columns((pl.col('x') * 2).alias('y'))` | Polars 用表达式 + alias |
| `np.where(cond, a, b)` | `pl.when(cond).then(a).otherwise(b)` | Polars 内置条件表达式 |
| `df['col'].map({1: 'a', 2: 'b'})` | `pl.col('col').map_dict({1: 'a', 2: 'b'})` | 映射用 map_dict |

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

注意：`with_columns` 返回新 DataFrame，原 `df` 不变。多个派生列可以在同一个 `with_columns` 中写完。

## 条件分层

`pl.when().then().otherwise()` 是 Polars 中的 if-else 表达式：

```python
result = df.with_columns(
    pl.when(pl.col("price") >= 500)
    .then(pl.lit("高价"))
    .when(pl.col("price") >= 200)
    .then(pl.lit("中价"))
    .otherwise(pl.lit("低价"))
    .alias("price_band")
)
```

注意：条件从上往下匹配，第一个满足的就生效，类似 `if-elif-else`。

## 练习

基于以下数据，完成 4 个动作：

```python
import polars as pl

products = pl.DataFrame({
    "product": ["键盘", "鼠标", "显示器", "耳机", "音箱"],
    "price": [199, 89, 1299, 299, 450],
    "cost": [120, 45, 800, 150, 280],
    "quantity": [5, 12, 2, 7, 3],
})
```

**动作 1**：用 `with_columns` 添加 `revenue`（收入 = price × quantity）和 `profit`（利润 = (price - cost) × quantity）。

**动作 2**：添加 `discount_price`（9 折价格 = price × 0.9），保留两位小数。

**动作 3**：用 `pl.when().then().otherwise()` 添加 `profit_level`：利润 ≥ 1000 为"高利润"，≥ 300 为"中利润"，其余为"低利润"。

**动作 4**：把以上步骤串起来，最终只保留 `product`、`revenue`、`profit`、`profit_level` 四列。

```python:example
import polars as pl

products = pl.DataFrame({
    "product": ["键盘", "鼠标", "显示器", "耳机", "音箱"],
    "price": [199, 89, 1299, 299, 450],
    "cost": [120, 45, 800, 150, 280],
    "quantity": [5, 12, 2, 7, 3],
})

result = products.with_columns(
    (pl.col("price") * pl.col("quantity")).alias("revenue"),
    ((pl.col("price") - pl.col("cost")) * pl.col("quantity")).alias("profit"),
).with_columns(
    pl.when(pl.col("profit") >= 1000)
    .then(pl.lit("高利润"))
    .when(pl.col("profit") >= 300)
    .then(pl.lit("中利润"))
    .otherwise(pl.lit("低利润"))
    .alias("profit_level")
).select(["product", "revenue", "profit", "profit_level"])

print(result)
```

## 常见错误

**错误 1：忘记 alias，列名变成表达式字符串**
```python
# 列名会自动生成为不太可读的字符串
df.with_columns(pl.col("price") * 1.1)

# 建议始终用 alias 命名
df.with_columns((pl.col("price") * 1.1).alias("new_price"))
```

**错误 2：when 条件顺序错误**
```python
# 错误：>= 100 会匹配所有 >= 1000 的行，后面的条件永远不会触发
pl.when(pl.col("x") >= 100).then(...)
  .when(pl.col("x") >= 1000).then(...)

# 正确：从最严格的条件开始
pl.when(pl.col("x") >= 1000).then(...)
  .when(pl.col("x") > 100).then(...)
```

**错误 3：在 when 中用 Python 原生比较**
```python
# 错误：'price' > 100 在 Python 中是比较字符串，不是列操作
pl.when('price' > 100).then(...)

# 正确：用 pl.col() 引用列
pl.when(pl.col("price") > 100).then(...)
```

## 下一步建议

完成本课后，建议继续：
- **Polars 数据清洗**：学习缺失值处理、类型转换等清洗操作
- 在 Playground 中尝试对你的数据做条件分层（如按金额分为大/中/小单）
