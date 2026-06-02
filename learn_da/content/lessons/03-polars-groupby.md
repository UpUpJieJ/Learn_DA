---
id: 3
slug: polars-groupby
title: Polars 分组聚合
category: polars
difficulty: intermediate
estimated_minutes: 30
order: 3
tags: [polars, group_by, agg, 聚合, window_functions]
prev_lesson:
  slug: duckdb-analytics
  title: DuckDB 查询分析
practice_objective: >-
  掌握 Polars 的 group_by + agg 分组聚合模式，
  能把 Pandas 的 groupby().agg() 迁移到 Polars 表达式写法。
completion_criteria:
  - 用 group_by 按单列分组并执行至少两种聚合
  - 用 over() 实现窗口函数（组内排名或组内占比）
  - 结果按聚合值排序
# Phase 3: 建议系统元数据
track: polars_basics
prerequisites: [polars-basics]
recommended_next: [polars-expressions, polars-cleaning]
skill_tags: [group_by, aggregation, window_functions, over]
is_review_friendly: false
is_branch_point: false
---

# Polars 分组聚合

## Pandas → Polars 对照

如果你用过 Pandas 的 `groupby`，下面这张表能帮你快速建立对应关系：

| Pandas | Polars | 说明 |
|--------|--------|------|
| `df.groupby('col')` | `df.group_by('col')` | 方法名下划线分隔 |
| `.agg({'sales': 'sum'})` | `.agg(pl.col('sales').sum())` | Polars 用表达式，不用字典 |
| `.groupby('col')['val'].transform('sum')` | `.with_columns(pl.col('val').sum().over('col'))` | Polars 用 `over()` 做窗口 |
| `.groupby(['a','b']).agg(...)` | `.group_by(['a','b']).agg(...)` | 多列分组写法一样 |

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

窗口函数可以在不分组的情况下，把聚合结果"广播"回每一行：

```python
# 每行都能看到自己所在 team 的总销售额
result = df.with_columns(
    pl.col('sales').sum().over('team').alias('team_total')
)
```

这在 Pandas 中对应 `groupby().transform()`。

## 练习

基于以下销售数据完成练习：

```python
import polars as pl

sales = pl.DataFrame({
    'region': ['华东', '华东', '华南', '华南', '华北', '华北'],
    'product': ['A', 'B', 'A', 'B', 'A', 'B'],
    'amount': [120, 80, 200, 150, 90, 300],
    'quantity': [3, 2, 5, 4, 2, 8],
})
```

**动作 1**：按 `region` 分组，计算每个区域的总销售额和平均销售额。

**动作 2**：按 `region` 和 `product` 双列分组，计算每组的总金额。

**动作 3**：用 `over()` 窗口函数，给每行添加一列 `region_total`（该行所属区域的总销售额），然后计算每笔订单占区域总额的比例。

```python:example
import polars as pl

sales = pl.DataFrame({
    'region': ['华东', '华东', '华南', '华南', '华北', '华北'],
    'product': ['A', 'B', 'A', 'B', 'A', 'B'],
    'amount': [120, 80, 200, 150, 90, 300],
    'quantity': [3, 2, 5, 4, 2, 8],
})

# 按区域分组统计
region_stats = sales.group_by('region').agg(
    pl.col('amount').sum().alias('total_amount'),
    pl.col('amount').mean().alias('avg_amount'),
)
print(region_stats.sort('region'))

# 窗口函数：计算占比
with_region = sales.with_columns(
    pl.col('amount').sum().over('region').alias('region_total'),
).with_columns(
    (pl.col('amount') / pl.col('region_total')).round(2).alias('ratio')
)
print(with_region)
```

## 常见错误

**错误 1：agg 中忘记给结果起别名**
```python
# 结果列名会自动生成，但可读性差
df.group_by('team').agg(pl.col('sales').sum())

# 建议显式起别名
df.group_by('team').agg(pl.col('sales').sum().alias('total'))
```

**错误 2：混淆 group_by + agg 和 over**
```python
# group_by + agg：结果行数减少（每组一行）
df.group_by('team').agg(pl.col('sales').sum())

# over：结果行数不变（聚合值广播回每行）
df.with_columns(pl.col('sales').sum().over('team'))
```

**错误 3：多列分组时用了嵌套列表**
```python
# 正确：一个列表包含所有分组列
df.group_by(['team', 'region'])
```

## 下一步建议

- 对比 DuckDB 中的 `GROUP BY` 写法，理解两种表达方式的差异
- 尝试在 Playground 中用 `over()` 计算组内排名（`rank`）
