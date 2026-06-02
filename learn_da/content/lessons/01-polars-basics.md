---
id: 1
slug: polars-basics
title: Polars 基础入门
category: polars
difficulty: beginner
estimated_minutes: 20
order: 1
tags: [polars, dataframe, 入门, select, filter, with_columns]
next_lesson:
  slug: duckdb-analytics
  title: DuckDB 查询分析
practice_objective: >-
  掌握 Polars 的 DataFrame 创建、列选择、行筛选和列派生，
  能把 Pandas 中最常用的操作映射到 Polars 对应写法。
completion_criteria:
  - 使用 pl.DataFrame 创建包含至少 3 列的 DataFrame
  - 用 select 选取指定列
  - 用 filter 按条件筛选行
  - 用 with_columns 添加一个派生列
# Phase 3: 建议系统元数据
track: polars_basics
prerequisites: []
recommended_next: [duckdb-analytics, polars-groupby]
skill_tags: [dataframe_basics, column_selection, row_filtering, column_derivation]
is_review_friendly: true
is_branch_point: false
---

# Polars 基础入门

## 什么是 Polars？

Polars 是一个高性能的 DataFrame 库，使用 Rust 编写，提供 Python API。它在处理大数据集时比 Pandas 快得多，主要优势包括：

- **惰性求值 (Lazy Evaluation)** - 自动优化查询计划
- **并行处理** - 充分利用多核 CPU
- **内存高效** - 列式存储，缓存友好

## 从 Pandas 迁移的直觉对照

如果你用过 Pandas，下面这张表能帮你快速建立对应关系：

| Pandas | Polars | 说明 |
|--------|--------|------|
| `pd.DataFrame({...})` | `pl.DataFrame({...})` | 创建方式几乎一样 |
| `df[['col1', 'col2']]` | `df.select(['col1', 'col2'])` | Polars 用方法，不用索引 |
| `df[df['x'] > 10]` | `df.filter(pl.col('x') > 10)` | Polars 用 `pl.col()` 引用列 |
| `df.assign(y = df.x * 2)` | `df.with_columns((pl.col('x') * 2).alias('y'))` | Polars 用表达式 |

## 创建 DataFrame

使用字典创建 DataFrame 非常简单：

```python
import polars as pl

df = pl.DataFrame({
    'city': ['beijing', 'shanghai', 'shenzhen'],
    'sales': [120, 98, 135],
})
print(df)
```

## select 与 filter

`select` 用于选择列，`filter` 用于筛选行：

```python
# 选择列
df.select(['city', 'sales'])

# 筛选行：销售额大于 100 的记录（保留 beijing=120, shenzhen=135）
df.filter(pl.col('sales') > 100)
```

注意：Polars 中引用列用 `pl.col('列名')`，而不是 `df['列名']`。这是和 Pandas 最大的写法差异之一。

## with_columns

使用 `with_columns` 添加或修改列：

```python
result = df.with_columns(
    (pl.col('sales') * 1.1).alias('sales_next_year')
)
print(result)
```

`with_columns` 不会修改原 DataFrame，而是返回一个新的。

## 练习

基于以下数据，完成 4 个动作：

```python
import polars as pl

orders = pl.DataFrame({
    'product': ['键盘', '鼠标', '显示器', '耳机'],
    'price': [200, 80, 1500, 300],
    'quantity': [3, 5, 1, 2],
})
```

**动作 1**：用 `select` 只选取 `product` 和 `price` 两列。

**动作 2**：用 `filter` 筛选出价格大于 100 的商品。

**动作 3**：用 `with_columns` 添加一列 `total`，值为 `price * quantity`。

**动作 4**：把以上三步串起来，先加 `total` 列，再筛选 `total > 500` 的记录，最后只保留 `product` 和 `total`。

```python:example
import polars as pl

orders = pl.DataFrame({
    'product': ['键盘', '鼠标', '显示器', '耳机'],
    'price': [200, 80, 1500, 300],
    'quantity': [3, 5, 1, 2],
})

# 添加 total 列
with_total = orders.with_columns(
    (pl.col('price') * pl.col('quantity')).alias('total')
)

# 筛选并选择
result = with_total.filter(
    pl.col('total') > 500
).select(['product', 'total'])

print(result)
```

## 常见错误

**错误 1：用 Pandas 语法写 Polars**
```python
# Pandas 风格（在 Polars 中会报错）
df[df['sales'] > 100]

# 正确写法
df.filter(pl.col('sales') > 100)
```

**错误 2：忘记 `pl.col()`**
```python
# 错误：直接用字符串比较
df.filter('sales' > 100)

# 正确：用 pl.col() 引用列
df.filter(pl.col('sales') > 100)
```

**错误 3：以为 `with_columns` 会修改原对象**
```python
# 这不会改变 df，结果在 new_df 中
new_df = df.with_columns(...)
```

## 下一步建议

完成本课后，建议继续：
- **DuckDB 查询分析**：学习用 SQL 方式查询数据，对比 Polars 和 SQL 的表达差异
- 回到 Playground，尝试用你自己的数据创建 DataFrame 并做筛选
