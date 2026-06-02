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
practice_objective: >-
  掌握 Polars 中缺失值、重复值、类型转换的处理方法，
  能把一张"脏数据"清洗成可分析的干净表。
completion_criteria:
  - 用 null_count() 查看每列缺失数量
  - 用 fill_null() 填充缺失值（固定值或统计值）
  - 用 unique() 去重
  - 用 cast() 转换字段类型
  - 用 str.to_date() 解析日期字符串
# Phase 3: 建议系统元数据
track: polars_basics
prerequisites: ['polars-basics', 'polars-expressions']
recommended_next: ['polars-joins']
skill_tags: ['data_cleaning', 'missing_values', 'fill_null', 'cast', 'deduplication']
is_review_friendly: true
is_branch_point: false
---

# Polars 数据清洗

## Pandas → Polars 对照

| Pandas | Polars | 说明 |
|--------|--------|------|
| `df.isnull().sum()` | `df.null_count()` | 查看缺失数量 |
| `df.fillna(0)` | `df.fill_null(0)` | 用固定值填充 |
| `df['col'].fillna(df['col'].mean())` | `df.with_columns(pl.col('col').fill_null(pl.col('col').mean()))` | 用统计值填充 |
| `df.drop_duplicates(subset=['id'])` | `df.unique(subset=["id"], keep="first")` | 去重 |
| `df['col'].astype(float)` | `df.with_columns(pl.col('col').cast(pl.Float64))` | 类型转换 |
| `pd.to_datetime(df['col'])` | `df.with_columns(pl.col('col').str.to_date(...))` | 日期解析 |

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

# 查看缺失数量
print(df.null_count())

# 去重 + 填充
cleaned = (
    df.unique(subset=["user_id"], keep="first")
    .with_columns(
        pl.col("city").fill_null("未知"),
        pl.col("score").fill_null(pl.col("score").mean()),
    )
)

print(cleaned)
```

注意：`fill_null(pl.col("score").mean())` 会用该列的均值填充缺失。如果想用中位数，换成 `median()`。

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

## 练习

构造一张有脏数据的用户表，完成完整的清洗流程：

```python
import polars as pl

raw = pl.DataFrame({
    "user_id": [1, 2, 2, 3, 4, 5],
    "name": ["张三", "李四", "李四", "王五", "赵六", "钱七"],
    "city": ["北京", None, None, "上海", "深圳", None],
    "signup_date": ["2026-01-01", "2026-01-03", "2026-01-03", "abc", "2026-01-10", "2026-01-12"],
    "age": ["25", "30", "30", "22", "unknown", "28"],
})
```

**动作 1**：用 `null_count()` 查看每列的缺失数量。

**动作 2**：用 `unique(subset=["user_id"], keep="first")` 去除重复用户。

**动作 3**：用 `fill_null("未知")` 填充缺失的城市。

**动作 4**：把 `age` 列转为数值类型——先用 `replace` 把 `"unknown"` 替换为 `None`，再用 `cast(pl.Int32)`。

**动作 5**：把 `signup_date` 中无法解析的日期（如 `"abc"`）标记为异常——先尝试用 `str.to_date` 解析，看哪些变成了 `null`。

```python:example
import polars as pl

raw = pl.DataFrame({
    "user_id": [1, 2, 2, 3, 4, 5],
    "name": ["张三", "李四", "李四", "王五", "赵六", "钱七"],
    "city": ["北京", None, None, "上海", "深圳", None],
    "signup_date": ["2026-01-01", "2026-01-03", "2026-01-03", "abc", "2026-01-10", "2026-01-12"],
    "age": ["25", "30", "30", "22", "unknown", "28"],
})

cleaned = (
    raw.unique(subset=["user_id"], keep="first")
    .with_columns(
        pl.col("city").fill_null("未知"),
        pl.col("age")
        .replace("unknown", None)
        .cast(pl.Int32),
    )
)

print(cleaned.sort("user_id"))
```

## 常见错误

**错误 1：unique 忘记指定 subset**
```python
# 错误：整行完全相同才算重复，但 user_id=2 的 city 一个是 None 一个不是
df.unique()

# 正确：按关键字段去重
df.unique(subset=["user_id"], keep="first")
```

**错误 2：cast 前没有处理非数值字符串**
```python
# 错误："unknown" 无法转为 Int32，会报错
df.with_columns(pl.col("age").cast(pl.Int32))

# 正确：先替换再转换
df.with_columns(
    pl.col("age").replace("unknown", None).cast(pl.Int32)
)
```

**错误 3：误以为 fill_null 会修改原 DataFrame**
```python
# 这不会改变 df
df.fill_null("未知")

# 正确：赋值给新变量或用 with_columns
df = df.fill_null("未知")
```

## 下一步建议

完成本课后，建议继续：
- **Polars 连接与合并**：学习如何把多张表拼在一起
- 在 Playground 中尝试处理一份有缺失值的 CSV 数据
