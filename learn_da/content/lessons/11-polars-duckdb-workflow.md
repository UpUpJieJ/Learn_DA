---
id: 11
slug: polars-duckdb-workflow
title: Polars 与 DuckDB 组合工作流
category: combined
difficulty: advanced
estimated_minutes: 45
order: 11
tags: [polars, duckdb, workflow, 实战, integration]
prev_lesson:
  slug: polars-lazy-pipeline
  title: Polars 惰性流水线
practice_objective: >-
  掌握 Polars 清洗 + DuckDB SQL 分析的组合工作流，
  能独立完成"数据清洗 → 注册到 DuckDB → SQL 汇总分析"的完整链路。
completion_criteria:
  - 用 Polars 完成缺失值填充和条件派生列
  - 用 to_arrow() + con.register() 将 Polars DataFrame 注册到 DuckDB
  - 用 DuckDB SQL 对清洗后的数据做分组聚合
  - 整个流程可在一个脚本中顺序执行
# Phase 3: 建议系统元数据
track: combined_workflow
prerequisites: [polars-basics, duckdb-analytics, polars-lazy-pipeline]
recommended_next: []
skill_tags: [polars_duckdb_integration, data_pipeline, arrow, workflow]
is_review_friendly: false
is_branch_point: false
---

# Polars 与 DuckDB 组合工作流

## 为什么组合使用

Polars 和 DuckDB 都能做很多数据分析任务，但它们的表达方式不同：

- **Polars** 适合用表达式构建可组合的数据处理流水线（清洗、派生、过滤）
- **DuckDB** 适合用 SQL 快速表达连接、聚合、窗口函数
- 组合使用时，可以先用 Polars 清洗数据，再把结果注册到 DuckDB 中做 SQL 分析

## Polars → DuckDB 桥梁

关键两行代码：

```python
# 1. 把 Polars DataFrame 转成 Arrow 格式
arrow_table = df.to_arrow()

# 2. 注册到 DuckDB 连接中，之后可以用 SQL 查询
con.register('my_table', arrow_table)
```

## 从清洗到 SQL 分析

```python
import duckdb
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5, 6],
    "region": ["华东", "华东", "华南", "华南", "华北", None],
    "category": ["办公", "数码", "办公", "配件", "办公", "数码"],
    "amount": [120, 899, 240, 59, 180, 620],
})

# Polars 做清洗：填充缺失值 + 派生列
clean_orders = orders.with_columns(
    pl.col("region").fill_null("未知"),
    pl.when(pl.col("amount") >= 500)
    .then(pl.lit("大额"))
    .otherwise(pl.lit("普通"))
    .alias("amount_band"),
)

# 注册到 DuckDB
con = duckdb.connect()
con.register("orders", clean_orders.to_arrow())

# DuckDB SQL 做汇总分析
result = con.execute("""
    WITH region_summary AS (
        SELECT
            region,
            amount_band,
            COUNT(*) AS order_count,
            SUM(amount) AS total_amount
        FROM orders
        GROUP BY region, amount_band
    )
    SELECT
        region,
        amount_band,
        order_count,
        total_amount,
        RANK() OVER (ORDER BY total_amount DESC) AS amount_rank
    FROM region_summary
    ORDER BY amount_rank
""").fetchall()

print(result)
```

## 工作流建议

一个清晰的组合流程通常包括：

1. 数据进入 Polars，先统一类型、处理缺失值
2. 用 Polars 表达式生成业务字段
3. 将处理后的表注册给 DuckDB
4. 用 SQL 写汇总、排名、分层分析
5. 回到 Polars 或 Python 中继续展示结果

## 练习

设计一个小型销售分析项目，完整走一遍组合流程：

**动作 1**：用 Polars 构造一张订单表（至少 6 行），包含 `order_id`、`region`、`category`、`amount`，故意留一两个缺失值。

**动作 2**：用 Polars 完成清洗——填充缺失 region、添加一个 `amount_band`（大额/普通）派生列。

**动作 3**：把清洗后的数据注册到 DuckDB，用 SQL 按 `region` 和 `amount_band` 分组统计订单数和总金额。

**动作 4**：在 SQL 中用 `RANK()` 窗口函数给每个分组排名。

```python:example
import duckdb
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5, 6],
    "region": ["华东", "华东", "华南", "华南", "华北", None],
    "category": ["办公", "数码", "办公", "配件", "办公", "数码"],
    "amount": [120, 899, 240, 59, 180, 620],
})

clean_orders = orders.with_columns(
    pl.col("region").fill_null("未知"),
    pl.when(pl.col("amount") >= 500)
    .then(pl.lit("大额"))
    .otherwise(pl.lit("普通"))
    .alias("amount_band"),
)

con = duckdb.connect()
con.register("orders", clean_orders.to_arrow())

result = con.execute("""
    SELECT region, SUM(amount) AS total_amount
    FROM orders
    GROUP BY region
    ORDER BY total_amount DESC
""").fetchall()

print(result)
```

## 常见错误

**错误 1：忘记注册就直接查询**
```python
# 错误：DuckDB 不知道 df 是什么
con.execute("SELECT * FROM df")

# 正确：先注册
con.register("df", df.to_arrow())
con.execute("SELECT * FROM df")
```

**错误 2：用 Polars 语法在 DuckDB SQL 中写**
```sql
-- 错误：pl.col() 是 Python，不是 SQL
SELECT pl.col('amount') FROM orders

-- 正确：标准 SQL
SELECT amount FROM orders
```

**错误 3：清洗不充分就交给 SQL**
```python
# 如果 Polars 阶段不处理缺失值，SQL 中可能出现意外 NULL
# 建议：清洗在 Polars 做，汇总在 DuckDB 做
```

## 下一步建议

- 尝试用这个工作流处理你自己的数据（CSV 文件 → Polars 读取 → 清洗 → DuckDB 分析）
- 对比"全 Polars"和"Polars + DuckDB"两种写法，体会各自的适用场景
