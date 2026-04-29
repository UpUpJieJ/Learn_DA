---
id: 8
slug: duckdb-joins-cte
title: DuckDB JOIN 与 CTE
category: duckdb
difficulty: intermediate
estimated_minutes: 35
order: 8
tags: [duckdb, join, cte, sql]
prev_lesson:
  slug: duckdb-sql-foundations
  title: DuckDB SQL 分析基础
next_lesson:
  slug: duckdb-window-functions
  title: DuckDB 窗口函数
---

# DuckDB JOIN 与 CTE

## 学习目标

- 使用 SQL `JOIN` 合并多张表
- 用 CTE 拆分复杂查询
- 构建清晰的分析 SQL

## 核心概念

CTE 是 Common Table Expression 的缩写，写法是 `WITH name AS (...)`。它可以把复杂 SQL 拆成多个有名字的中间步骤，让查询更像一条分析流程。

`JOIN` 常用于把事实表和维度表合并：

- 订单表：谁在什么时候买了什么
- 商品表：商品属于哪个品类，成本是多少
- 用户表：用户来自哪个城市或渠道

## 用 CTE 组织分析

```python
import duckdb

con = duckdb.connect()
con.execute("""
    CREATE TABLE orders AS
    SELECT * FROM (VALUES
        (101, 1, 2),
        (102, 2, 1),
        (103, 1, 3),
        (104, 3, 4)
    ) AS t(order_id, product_id, quantity)
""")
con.execute("""
    CREATE TABLE products AS
    SELECT * FROM (VALUES
        (1, '办公', 120),
        (2, '数码', 899),
        (3, '配件', 59)
    ) AS t(product_id, category, unit_price)
""")

result = con.execute("""
    WITH order_detail AS (
        SELECT
            o.order_id,
            p.category,
            o.quantity * p.unit_price AS amount
        FROM orders o
        LEFT JOIN products p USING (product_id)
    )
    SELECT category, SUM(amount) AS total_amount
    FROM order_detail
    GROUP BY category
    ORDER BY total_amount DESC
""").fetchall()

print(result)
```

## 何时使用 CTE

当一条 SQL 同时包含连接、字段计算、过滤、聚合时，建议用 CTE 分层。每个 CTE 只做一件事：清洗、补字段、算指标或汇总。

## 练习建议

继续扩展示例：

- 增加用户表并连接到订单明细
- 用 CTE 先算订单金额，再按用户城市汇总
- 对比 `LEFT JOIN` 和 `INNER JOIN` 的结果差异

```python:example
import duckdb

con = duckdb.connect()
con.execute("CREATE TABLE orders AS SELECT * FROM (VALUES (101, 1, 2), (102, 2, 1), (103, 1, 3), (104, 3, 4)) AS t(order_id, product_id, quantity)")
con.execute("CREATE TABLE products AS SELECT * FROM (VALUES (1, '办公', 120), (2, '数码', 899), (3, '配件', 59)) AS t(product_id, category, unit_price)")

result = con.execute("""
    WITH detail AS (
        SELECT p.category, o.quantity * p.unit_price AS amount
        FROM orders o
        LEFT JOIN products p USING (product_id)
    )
    SELECT category, SUM(amount) AS total_amount
    FROM detail
    GROUP BY category
    ORDER BY total_amount DESC
""").fetchall()

print(result)
```
