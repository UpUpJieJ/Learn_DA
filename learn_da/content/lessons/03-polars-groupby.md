---
id: 3
slug: polars-groupby
title: Polars 分组聚合
category: polars
difficulty: intermediate
estimated_minutes: 30
order: 3
tags: [polars, group_by, agg, 聚合]
prev_lesson:
  slug: duckdb-analytics
  title: DuckDB 查询分析
---

# Polars 分组聚合

## group_by 分组

Polars 使用 `group_by` 按列分组，然后用 `agg` 进行聚合：

```python
import polars as pl

df = pl.DataFrame({
    'team': ['A', 'A', 'B', 'B'],
    'sales': [10, 20, 30, 40],
})

result = df.group_by('team').agg(
    pl.col('sales').sum().alias('total_sales'),
    pl.col('sales').mean().alias('avg_sales'),
    pl.col('sales').count().alias('count'),
)
print(result.sort('team'))
```

## 常用聚合函数

| 函数 | 说明 |
|------|------|
| `sum()` | 求和 |
| `mean()` / `avg()` | 平均值 |
| `min()` / `max()` | 最小/最大值 |
| `count()` | 计数 |
| `std()` / `var()` | 标准差/方差 |
| `first()` / `last()` | 第一个/最后一个值 |

## 多列分组

```python
result = df.group_by(['team', 'region']).agg(
    pl.col('sales').sum().alias('total_sales')
)
```

## 窗口函数

Polars 也支持窗口函数：

```python
result = df.with_columns(
    pl.col('sales').sum().over('team').alias('team_total')
)
```

```python:example
import polars as pl

df = pl.DataFrame({
    'team': ['A', 'A', 'B', 'B'],
    'sales': [10, 20, 30, 40],
})

result = df.group_by('team').agg(
    pl.col('sales').sum().alias('total_sales')
)
print(result.sort('team'))
```
