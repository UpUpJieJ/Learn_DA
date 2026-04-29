---
id: 9
slug: duckdb-window-functions
title: DuckDB 窗口函数
category: duckdb
difficulty: intermediate
estimated_minutes: 35
order: 9
tags: [duckdb, window function, rank, sql]
prev_lesson:
  slug: duckdb-joins-cte
  title: DuckDB JOIN 与 CTE
next_lesson:
  slug: polars-lazy-pipeline
  title: Polars 惰性流水线
---

# DuckDB 窗口函数

## 学习目标

- 理解窗口函数和普通聚合的区别
- 使用 `ROW_NUMBER`、`RANK`、累计求和
- 在保留明细行的同时计算分组指标

## 核心概念

普通 `GROUP BY` 会把多行压缩成一行；窗口函数则会保留原始明细行，并在每一行旁边追加分组计算结果。

典型语法：

```sql
函数() OVER (
    PARTITION BY 分组字段
    ORDER BY 排序字段
)
```

## 给每个区域内订单排名

```python
import duckdb

con = duckdb.connect()
con.execute("""
    CREATE TABLE orders AS
    SELECT * FROM (VALUES
        (1, '华东', '2026-01-01', 120),
        (2, '华东', '2026-01-02', 300),
        (3, '华东', '2026-01-03', 180),
        (4, '华南', '2026-01-01', 90),
        (5, '华南', '2026-01-02', 260)
    ) AS t(order_id, region, order_date, amount)
""")

result = con.execute("""
    SELECT
        order_id,
        region,
        order_date,
        amount,
        RANK() OVER (
            PARTITION BY region
            ORDER BY amount DESC
        ) AS amount_rank,
        SUM(amount) OVER (
            PARTITION BY region
            ORDER BY order_date
        ) AS running_amount
    FROM orders
    ORDER BY region, order_date
""").fetchall()

print(result)
```

## 常见窗口函数

- `ROW_NUMBER()`：连续编号
- `RANK()`：排名，相同值会并列并跳号
- `DENSE_RANK()`：排名，相同值并列但不跳号
- `SUM(...) OVER (...)`：累计值或分组总值
- `AVG(...) OVER (...)`：窗口平均值

## 练习建议

基于订单数据完成：

- 找出每个区域金额最高的订单
- 计算每个区域的累计销售额
- 给每个区域内订单按日期编号

```python:example
import duckdb

con = duckdb.connect()
con.execute("""
    CREATE TABLE orders AS
    SELECT * FROM (VALUES
        (1, '华东', '2026-01-01', 120),
        (2, '华东', '2026-01-02', 300),
        (3, '华南', '2026-01-01', 90),
        (4, '华南', '2026-01-02', 260)
    ) AS t(order_id, region, order_date, amount)
""")

result = con.execute("""
    SELECT
        order_id,
        region,
        amount,
        ROW_NUMBER() OVER (PARTITION BY region ORDER BY amount DESC) AS rank_in_region
    FROM orders
    ORDER BY region, rank_in_region
""").fetchall()

print(result)
```
