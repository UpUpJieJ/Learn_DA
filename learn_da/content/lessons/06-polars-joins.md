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
practice_objective: >-
  掌握 Polars 的 join 操作，能用 left join 补充维度字段、
  用 anti join 做数据质量检查。
completion_criteria:
  - 用 join + on + how="left" 连接两张表
  - 连接后用 with_columns 计算派生字段
  - 用 how="anti" 找出未匹配的记录
  - 理解 left / inner / outer / semi / anti 的区别
# Phase 3: 建议系统元数据
track: polars_basics
prerequisites: ['polars-basics', 'polars-cleaning']
recommended_next: ['duckdb-sql-foundations', 'polars-lazy-pipeline']
skill_tags: ['join', 'left_join', 'anti_join', 'data_modeling']
is_review_friendly: false
is_branch_point: true
---

# Polars 连接与合并

## Pandas → Polars 对照

| Pandas | Polars | 说明 |
|--------|--------|------|
| `df.merge(dim, on='id', how='left')` | `df.join(dim, on="id", how="left")` | 方法名不同 |
| `df.merge(dim, left_on='a', right_on='b')` | `df.join(dim, left_on="a", right_on="b")` | 不同列名连接 |
| `pd.concat([df1, df2])` | `pl.concat([df1, df2])` | 纵向拼接 |

## 核心概念

数据分析中经常把多张表合并。例如订单表记录交易，商品表记录品类和成本。连接可以把分散的信息组织成一张分析宽表。

常见连接类型：

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `left` | 保留左表所有记录 | 给事实表补充维度信息 |
| `inner` | 只保留两边都匹配的记录 | 需要严格关联数据 |
| `outer` | 保留两边所有记录 | 合并两个独立数据集 |
| `semi` | 保留左表中能匹配右表的记录 | 过滤出"有关联的"记录 |
| `anti` | 保留左表中不能匹配右表的记录 | 数据质量检查 |

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

注意：`join` 默认是 `inner`，分析中推荐显式写 `how="left"` 以避免意外丢失行。

## 找出未匹配记录

```python
# 找出 product_id 在商品表中不存在的订单
unknown_orders = orders.join(products, on="product_id", how="anti")
```

`anti` 连接很适合做数据质量检查：订单里是否出现了商品维表不存在的商品编号。

## 练习

基于以下数据，完成 4 个动作：

```python
import polars as pl

orders = pl.DataFrame({
    "order_id": [101, 102, 103, 104, 105],
    "user_id": [1, 2, 1, 3, 99],
    "product_id": [1, 2, 1, 3, 2],
    "quantity": [2, 1, 5, 3, 1],
})

users = pl.DataFrame({
    "user_id": [1, 2, 3],
    "city": ["北京", "上海", "深圳"],
})

products = pl.DataFrame({
    "product_id": [1, 2, 3],
    "category": ["办公", "数码", "配件"],
    "unit_price": [120, 899, 59],
})
```

**动作 1**：用 `left join` 给订单补充用户城市信息。

**动作 2**：再用 `left join` 给订单补充商品品类和单价，然后计算每笔订单的金额（quantity × unit_price）。

**动作 3**：按城市统计总订单金额，找出消费最高的城市。

**动作 4**：用 `anti join` 找出 user_id 在用户表中不存在的订单（数据质量检查）。

```python:example
import polars as pl

orders = pl.DataFrame({
    "order_id": [101, 102, 103, 104, 105],
    "user_id": [1, 2, 1, 3, 99],
    "product_id": [1, 2, 1, 3, 2],
    "quantity": [2, 1, 5, 3, 1],
})

users = pl.DataFrame({
    "user_id": [1, 2, 3],
    "city": ["北京", "上海", "深圳"],
})

products = pl.DataFrame({
    "product_id": [1, 2, 3],
    "category": ["办公", "数码", "配件"],
    "unit_price": [120, 899, 59],
})

result = (
    orders
    .join(users, on="user_id", how="left")
    .join(products, on="product_id", how="left")
    .with_columns(
        (pl.col("quantity") * pl.col("unit_price")).alias("amount")
    )
)

# 按城市统计
city_stats = (
    result.group_by("city")
    .agg(pl.col("amount").sum().alias("total_amount"))
    .sort("total_amount", descending=True)
)
print(city_stats)

# 数据质量检查
bad_orders = orders.join(users, on="user_id", how="anti")
print(bad_orders)
```

## 常见错误

**错误 1：join 后列名冲突**
```python
# 如果两张表有同名列（除 join key 外），Polars 会自动加后缀 _right
# 建议 join 前检查列名，或用 select 明确保留哪些列
```

**错误 2：忘记指定 how，默认 inner 丢了行**
```python
# 默认 inner，可能丢失没有匹配的行
orders.join(users, on="user_id")

# 分析中推荐显式 left
orders.join(users, on="user_id", how="left")
```

**错误 3：多列连接时用 on 和 left_on/right_on 混淆**
```python
# 同名列连接：用 on
df.join(dim, on="product_id", how="left")

# 不同名列连接：用 left_on + right_on
df.join(dim, left_on="prod_id", right_on="id", how="left")
```

## 下一步建议

完成本课后，建议继续：
- **DuckDB SQL 分型基础**：学习用 SQL 的 JOIN 写法做同样的事情
- 对比 Polars join 和 SQL JOIN 的写法差异
