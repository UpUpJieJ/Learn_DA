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
practice_objective: >-
  掌握用 DuckDB 执行 SQL 查询的基本流程，能用 SELECT、WHERE、GROUP BY、ORDER BY
  从明细数据中提取汇总指标。
completion_criteria:
  - 用 CREATE TABLE AS VALUES 构造测试数据
  - 用 SELECT + WHERE 筛选行
  - 用 GROUP BY + 聚合函数做分组统计
  - 用 ORDER BY 排序结果
  - 用 HAVING 过滤分组后的结果
# Phase 3: 建议系统元数据
track: duckdb_basics
prerequisites: ['duckdb-analytics']
recommended_next: ['duckdb-joins-cte']
skill_tags: ['sql_basics', 'select', 'where', 'group_by', 'having', 'order_by']
is_review_friendly: true
is_branch_point: false
---

# DuckDB SQL 分析基础

## SQL → DuckDB 对照

如果你写过 MySQL 或 PostgreSQL，DuckDB 的 SQL 几乎没有学习成本：

| 场景 | MySQL / PostgreSQL | DuckDB | 说明 |
|------|-------------------|--------|------|
| 建表 | `CREATE TABLE ... INSERT INTO` | `CREATE TABLE AS SELECT * FROM (VALUES ...)` | DuckDB 可以一步到位 |
| 查询 | 标准 SQL | 标准 SQL | 完全兼容 |
| 无需服务器 | 需要 | 不需要 | DuckDB 嵌入 Python 进程 |

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

## 练习

基于上面的订单表，完成以下查询：

**动作 1**：按品类（category）统计订单数和总金额，只保留总金额大于 200 的品类，按总金额从高到低排序。

**动作 2**：在上面的查询基础上，增加一列 `avg_amount`（该品类的平均订单金额）。

**动作 3**：写一个查询，找出"华东"区域中金额最高的那一笔订单的所有字段。

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
        SUM(amount) AS total_amount,
        AVG(amount) AS avg_amount
    FROM orders
    GROUP BY category
    HAVING SUM(amount) > 200
    ORDER BY total_amount DESC
""").fetchall()

print(result)
```

## 常见错误

**错误 1：WHERE 中使用聚合函数**
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

**错误 2：忘记 GROUP BY**
```sql
-- 错误：混合了聚合列和非聚合列
SELECT category, SUM(amount) FROM orders

-- 正确：非聚合列必须出现在 GROUP BY 中
SELECT category, SUM(amount) FROM orders GROUP BY category
```

**错误 3：列名拼写或大小写**
```sql
-- DuckDB 默认不区分大小写，但建议和建表时保持一致
SELECT Region FROM orders  -- 可以工作
SELECT region FROM orders  -- 推荐
```

## 下一步建议

- 学习 **JOIN 与 CTE**：把多张表连接起来做更复杂的分析
- 尝试在 DuckDB 中直接查询 Polars DataFrame（用 `con.register()`）
