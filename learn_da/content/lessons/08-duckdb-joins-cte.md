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
practice_objective: >-
  掌握用 JOIN 合并多表数据、用 CTE 拆分复杂查询的写法，
  能独立构建"连接 → 计算 → 汇总"的分析 SQL。
completion_criteria:
  - 用 LEFT JOIN 连接两张表
  - 用 CTE (WITH ... AS) 拆分查询步骤
  - 在 CTE 中计算派生字段后做分组聚合
  - 对比 LEFT JOIN 和 INNER JOIN 的结果差异
# Phase 3: 建议系统元数据
track: duckdb_advanced
prerequisites: ['duckdb-sql-foundations']
recommended_next: ['duckdb-window-functions']
skill_tags: ['join', 'cte', 'with_clause', 'multi_table']
is_review_friendly: false
is_branch_point: false
---

# DuckDB JOIN 与 CTE

## 核心概念

CTE 是 Common Table Expression 的缩写，写法是 `WITH name AS (...)`。它可以把复杂 SQL 拆成多个有名字的中间步骤，让查询更像一条分析流程。

`JOIN` 常用于把事实表和维度表合并：

- 订单表：谁在什么时候买了什么
- 商品表：商品属于哪个品类，成本是多少
- 用户表：用户来自哪个城市或渠道

## JOIN 类型速查

| JOIN 类型 | 说明 | 使用场景 |
|-----------|------|----------|
| `INNER JOIN` | 只保留两表都匹配的行 | 需要严格关联数据时 |
| `LEFT JOIN` | 保留左表全部，右表匹配不上填 NULL | 以事实表为主，不能丢行时 |
| `CROSS JOIN` | 笛卡尔积，每行配每行 | 生成组合矩阵时 |

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

## 练习

基于上面的 `orders` 和 `products` 表，完成以下练习：

**动作 1**：添加一张用户表，包含 `user_id` 和 `city` 字段，然后用 JOIN 把订单和用户连接起来。

**动作 2**：用 CTE 先算出每笔订单的金额（quantity × unit_price），再按城市汇总总消费。

**动作 3**：对比 `LEFT JOIN` 和 `INNER JOIN`——在 orders 表中加一条 `product_id = 99`（products 表中不存在）的记录，观察两种 JOIN 的结果差异。

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

## 常见错误

**错误 1：JOIN 后忘记去重或聚合**
```sql
-- JOIN 可能产生重复行，直接 COUNT 会偏大
SELECT COUNT(*) FROM orders o LEFT JOIN products p USING (product_id)
-- 先想清楚你要数什么，再写查询
```

**错误 2：混淆 WHERE 和 ON 的过滤时机**
```sql
-- ON 中的条件在 JOIN 时过滤（影响是否匹配）
-- WHERE 中的条件在 JOIN 后过滤（影响最终结果）
SELECT * FROM orders o
LEFT JOIN products p ON o.product_id = p.product_id AND p.category = '办公'
-- 这里的 AND p.category = '办公' 会在 JOIN 阶段过滤，LEFT JOIN 可能产生 NULL 行
```

**错误 3：CTE 嵌套过深失去可读性**
```sql
-- 建议每个 CTE 只做一件事，用有意义的命名
WITH raw_orders AS (...),
     order_amounts AS (...),
     category_summary AS (...)
SELECT * FROM category_summary
```

## 下一步建议

- 学习 **窗口函数**：在不折叠行的情况下做组内计算
- 尝试用 CTE 构建一个"订单明细 → 品类汇总 → 排名"的完整分析链
