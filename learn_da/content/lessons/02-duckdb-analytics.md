---
id: 2
slug: duckdb-analytics
title: DuckDB 查询分析
category: duckdb
difficulty: beginner
estimated_minutes: 25
order: 2
tags: [duckdb, sql, 分析, group_by, aggregation]
prev_lesson:
  slug: polars-basics
  title: Polars 基础入门
next_lesson:
  slug: polars-groupby
  title: Polars 分组聚合
practice_objective: >-
  掌握 DuckDB 的基本使用流程：建表、查询、聚合、排序，
  能用 SQL 从明细数据中提取汇总指标。
completion_criteria:
  - 用 con = duckdb.connect() 创建内存连接
  - 用 CREATE TABLE AS VALUES 构造测试数据
  - 用 SELECT + GROUP BY 做分组聚合
  - 用 ORDER BY 对结果排序
# Phase 3: 建议系统元数据
track: duckdb_basics
prerequisites: []
recommended_next: [polars-groupby, duckdb-joins-cte]
skill_tags: [sql_basics, group_by, aggregation, sorting]
is_review_friendly: true
is_branch_point: false
---

# DuckDB 查询分析

## 什么是 DuckDB？

DuckDB 是一个嵌入式分析数据库，专为 OLAP 工作负载设计。它可以直接在 Python 进程中运行，无需安装服务器。

主要特点：
- **零配置** - 无需安装服务器，`pip install duckdb` 即可使用
- **高性能** - 列式存储，向量化执行
- **SQL 兼容** - 支持标准 SQL 语法

## SQL → Polars 对照

如果你已经学过 Polars，下面这张表能帮你理解 SQL 和 Polars 的对应关系：

| 操作 | Polars | SQL (DuckDB) |
|------|--------|-------------|
| 选择列 | `df.select(['a', 'b'])` | `SELECT a, b FROM t` |
| 筛选行 | `df.filter(pl.col('x') > 10)` | `WHERE x > 10` |
| 分组聚合 | `df.group_by('g').agg(pl.col('v').sum())` | `GROUP BY g` + `SUM(v)` |
| 排序 | `df.sort('v', descending=True)` | `ORDER BY v DESC` |
| 添加列 | `df.with_columns(...)` | `SELECT *, expr AS new_col` |

## 内存连接

```python
import duckdb

con = duckdb.connect()  # 内存数据库，关闭连接后数据消失
```

DuckDB 的默认连接是内存数据库，适合临时分析和学习。不需要启动任何服务。

## 创建表和查询

```python
import duckdb

con = duckdb.connect()

# 用 VALUES 直接构造测试数据
con.execute("""
    CREATE TABLE orders AS
    SELECT * FROM (VALUES
        (1, '华东', '办公', 120),
        (2, '华东', '数码', 899),
        (3, '华南', '办公', 240),
        (4, '华北', '配件', 59)
    ) AS t(order_id, region, category, amount)
""")

# 查询
result = con.execute("SELECT * FROM orders").fetchall()
print(result)
```

## 分组聚合

```python
result = con.execute("""
    SELECT
        region,
        COUNT(*) AS order_count,
        SUM(amount) AS total_amount,
        AVG(amount) AS avg_amount
    FROM orders
    GROUP BY region
    ORDER BY total_amount DESC
""").fetchall()

print(result)
```

注意：`GROUP BY` 后面的列必须和 `SELECT` 中非聚合列一致，否则会报错。

## 与 Polars 互通

DuckDB 可以直接查询 Polars DataFrame，无需手动导出：

```python
import polars as pl
import duckdb

df = pl.DataFrame({'id': [1, 2], 'name': ['Ada', 'Lin']})
con = duckdb.connect()

# 注册 Polars DataFrame 为 SQL 表
con.register('users', df.to_arrow())
result = con.execute('SELECT * FROM users').fetchall()
print(result)
```

## 练习

基于上面的 `orders` 表，完成以下查询：

**动作 1**：查询 `orders` 表的所有数据，确认表已创建成功。

**动作 2**：按 `category`（品类）分组，统计每个品类的订单数和总金额。

**动作 3**：在动作 2 的基础上，只保留总金额大于 200 的品类，并按总金额从高到低排序。

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
    SELECT
        category,
        COUNT(*) AS order_count,
        SUM(amount) AS total_amount
    FROM orders
    GROUP BY category
    HAVING SUM(amount) > 200
    ORDER BY total_amount DESC
""").fetchall()

print(result)
```

## 常见错误

**错误 1：WHERE 和 HAVING 混淆**
```sql
-- 错误：WHERE 不能过滤聚合结果
SELECT category, SUM(amount) FROM orders
WHERE SUM(amount) > 200
GROUP BY category

-- 正确：用 HAVING 过滤分组后的结果
SELECT category, SUM(amount) AS total FROM orders
GROUP BY category
HAVING SUM(amount) > 200
```

**错误 2：GROUP BY 缺少非聚合列**
```sql
-- 错误：category 不在 GROUP BY 中
SELECT category, region, SUM(amount) FROM orders
GROUP BY category

-- 正确：所有非聚合列都必须出现在 GROUP BY 中
SELECT category, region, SUM(amount) FROM orders
GROUP BY category, region
```

**错误 3：忘记给聚合列起别名**
```sql
-- 结果列名会自动生成为 sum(amount)，可读性差
SELECT category, SUM(amount) FROM orders GROUP BY category

-- 建议起别名
SELECT category, SUM(amount) AS total FROM orders GROUP BY category
```

## 下一步建议

完成本课后，建议继续：
- **Polars 分组聚合**：对比 Polars 的 `group_by` 和 SQL 的 `GROUP BY`，理解两种表达方式
- 在 Playground 中尝试用 `con.register()` 把 Polars DataFrame 注册到 DuckDB 查询
