---
id: 2
slug: duckdb-analytics
title: DuckDB 查询分析
category: duckdb
difficulty: beginner
estimated_minutes: 25
order: 2
tags: [duckdb, sql, 分析]
prev_lesson:
  slug: polars-basics
  title: Polars 基础入门
next_lesson:
  slug: polars-groupby
  title: Polars 分组聚合
---

# DuckDB 查询分析

## 什么是 DuckDB？

DuckDB 是一个嵌入式分析数据库，专为 OLAP 工作负载设计。它可以直接在 Python 进程中运行，无需安装服务器。

主要特点：
- **零配置** - 无需安装服务器
- **高性能** - 列式存储，向量化执行
- **SQL 兼容** - 支持标准 SQL

## 内存连接

```python
import duckdb

con = duckdb.connect()  # 内存数据库
```

## 创建表和查询

```python
con.execute("""
    CREATE TABLE orders AS
    SELECT * FROM (VALUES
        (1, 'A', 100),
        (2, 'A', 120),
        (3, 'B', 90)
    ) AS t(id, category, amount)
""")

result = con.execute("""
    SELECT category, AVG(amount) AS avg_amount
    FROM orders
    GROUP BY category
    ORDER BY avg_amount DESC
""").fetchall()
print(result)
```

## 与 Polars 互通

DuckDB 可以直接查询 Polars DataFrame：

```python
import polars as pl
import duckdb

df = pl.DataFrame({'id': [1, 2], 'name': ['Ada', 'Lin']})
con = duckdb.connect()
con.register('users', df.to_arrow())
print(con.execute('SELECT * FROM users').fetchall())
```

```python:example
import duckdb

con = duckdb.connect()
con.execute(
    "create table orders as select * from (values "
    "(1, 'A', 100), (2, 'A', 120), (3, 'B', 90)) "
    "as t(id, category, amount)"
)
print(
    con.execute(
        "select category, avg(amount) as avg_amount from orders "
        "group by category order by avg_amount desc"
    ).fetchall()
)
```
