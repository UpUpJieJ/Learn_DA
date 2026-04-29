---
id: 1
slug: polars-basics
title: Polars 基础入门
category: polars
difficulty: beginner
estimated_minutes: 20
order: 1
tags: [polars, dataframe, 入门]
next_lesson:
  slug: duckdb-analytics
  title: DuckDB 查询分析
---

# Polars 基础入门

## 什么是 Polars？

Polars 是一个高性能的 DataFrame 库，使用 Rust 编写，提供 Python API。它在处理大数据集时比 Pandas 快得多，主要优势包括：

- **惰性求值 (Lazy Evaluation)** - 自动优化查询计划
- **并行处理** - 充分利用多核 CPU
- **内存高效** - 列式存储，缓存友好

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

# 筛选行
df.filter(pl.col('sales') > 1100)
```

## with_columns

使用 `with_columns` 添加或修改列：

```python
result = df.with_columns(
    pl.col('sales').mean().alias('avg_sales')
)
```

## 课后练习

尝试创建一个包含以下数据的 DataFrame，并筛选出销售额大于 100 的记录：

| product | sales | region |
|---------|-------|--------|
| A       | 150   | North  |
| B       | 80    | South  |
| C       | 200   | North  |

```python:example
import polars as pl

df = pl.DataFrame({
    'city': ['beijing', 'shanghai', 'shenzhen'],
    'sales': [120, 98, 135],
})

result = df.with_columns(
    pl.col('sales').mean().alias('avg_sales')
)
print(result)
```
