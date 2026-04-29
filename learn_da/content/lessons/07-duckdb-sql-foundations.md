---
id: 7
slug: duckdb-sql-foundations
title: DuckDB SQL 分析基础
category: duckdb
difficulty: beginner
estimated_minutes: 30
order: 7
tags: [duckdb, sql, select, group by]
prev_lesson:
  slug: polars-joins
  title: Polars 连接与合并
next_lesson:
  slug: duckdb-joins-cte
  title: DuckDB JOIN 与 CTE
---

# DuckDB SQL 分析基础

## 学习目标

- 使用 DuckDB 执行基础 SQL 查询
- 掌握 `SELECT`、`WHERE`、`GROUP BY`、`ORDER BY`
- 从明细数据得到汇总指标

## 核心概念

DuckDB 适合在本地直接运行分析型 SQL。你可以把它理解为一个轻量但强大的分析数据库，尤其适合处理表格数据、临时分析和数据探索。

SQL 查询的常见顺序：

- `SELECT`：选择或计算输出字段
- `FROM`：指定数据来源
- `WHERE`：过滤明细行
- `GROUP BY`：分组
- `HAVING`：过滤分组结果
- `ORDER BY`：排序

## 汇总订单数据

```python
import duckdb

con = duckdb.connect()
con.execute("""
    CREATE TABLE orders AS
    SELECT * FROM (VALUES
        (1, '华东', '办公', 120),
        (2, '华东', '数码', 899),
        (3, '华南', '办公', 240),
        (4, '华北', '配件', 59)
    ) AS t(order_id, region, category, amount)
""")

result = con.execute("""
    SELECT
        region,
        COUNT(*) AS order_count,
        SUM(amount) AS total_amount,
        AVG(amount) AS avg_amount
    FROM orders
    WHERE amount >= 100
    GROUP BY region
    ORDER BY total_amount DESC
""").fetchall()

print(result)
```

## 使用别名提升可读性

给聚合结果起清晰的别名，可以让后续分析更容易理解。例如 `total_amount` 比 `sum(amount)` 更适合作为报表字段。

## 练习建议

基于订单表完成：

- 按品类统计订单数和总金额
- 只保留总金额大于 200 的品类
- 按总金额从高到低排序

```python:example
import duckdb

con = duckdb.connect()
con.execute("""
    CREATE TABLE orders AS
    SELECT * FROM (VALUES
        (1, '华东', '办公', 120),
        (2, '华东', '数码', 899),
        (3, '华南', '办公', 240),
        (4, '华北', '配件', 59)
    ) AS t(order_id, region, category, amount)
""")

result = con.execute("""
    SELECT category, COUNT(*) AS order_count, SUM(amount) AS total_amount
    FROM orders
    GROUP BY category
    HAVING SUM(amount) > 200
    ORDER BY total_amount DESC
""").fetchall()

print(result)
```
