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
practice_objective: >-
  掌握 SQL 窗口函数的核心写法，能用 ROW_NUMBER、RANK、SUM OVER
  在保留明细行的同时计算分组指标。
completion_criteria:
  - 用 RANK() OVER (PARTITION BY ... ORDER BY ...) 做组内排名
  - 用 SUM() OVER (...) 计算累计值
  - 用 ROW_NUMBER() 生成连续编号
  - 理解窗口函数和 GROUP BY 的区别
# Phase 3: 建议系统元数据
track: duckdb_advanced
prerequisites: ['duckdb-joins-cte']
recommended_next: ['polars-lazy-pipeline']
skill_tags: ['window_functions', 'rank', 'row_number', 'partition_by']
is_review_friendly: false
is_branch_point: false
---

# DuckDB 窗口函数

## GROUP BY vs 窗口函数

| 特性 | GROUP BY | 窗口函数 |
|------|----------|----------|
| 结果行数 | 减少（每组一行） | 不变（保留所有明细行） |
| 典型用途 | 汇总统计 | 组内排名、累计值、占比 |
| 语法 | `GROUP BY col` | `FUNC() OVER (PARTITION BY col)` |

一句话：`GROUP BY` 折叠行，窗口函数不折叠。

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

| 函数 | 说明 | 示例场景 |
|------|------|----------|
| `ROW_NUMBER()` | 连续编号，不并列 | 给每行一个唯一序号 |
| `RANK()` | 排名，相同值并列并跳号 | 销售额排名 |
| `DENSE_RANK()` | 排名，相同值并列不跳号 | 成绩排名 |
| `SUM(...) OVER (...)` | 累计值或分组总值 | 累计销售额 |
| `AVG(...) OVER (...)` | 窗口平均值 | 组内平均 |

## RANK vs DENSE_RANK

```sql
-- 假设金额为 100, 200, 200, 300
RANK()        -- 结果：1, 2, 2, 4（跳过了 3）
DENSE_RANK()  -- 结果：1, 2, 2, 3（不跳号）
```

## 练习

基于上面的 `orders` 表，完成以下查询：

**动作 1**：用 `RANK()` 给每个区域内的订单按金额降序排名。

**动作 2**：用 `SUM() OVER (...)` 计算每个区域的累计销售额（按日期累计）。

**动作 3**：用 `ROW_NUMBER()` 给所有订单按金额降序编号，找出金额最高的前 3 笔订单。

**动作 4**：在排名结果上用 CTE 或子查询，只保留每个区域排名第 1 的订单。

```python:example
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

# 每个区域排名第 1 的订单
result = con.execute("""
    WITH ranked AS (
        SELECT
            order_id,
            region,
            amount,
            RANK() OVER (
                PARTITION BY region
                ORDER BY amount DESC
            ) AS amount_rank
        FROM orders
    )
    SELECT * FROM ranked WHERE amount_rank = 1
""").fetchall()

print(result)
```

## 常见错误

**错误 1：忘记 PARTITION BY，排名变成全局**
```sql
-- 错误：所有订单混在一起排名
RANK() OVER (ORDER BY amount DESC)

-- 正确：按区域分组排名
RANK() OVER (PARTITION BY region ORDER BY amount DESC)
```

**错误 2：在 WHERE 中过滤窗口函数**
```sql
-- 错误：WHERE 不能过滤窗口函数结果
SELECT * FROM orders
WHERE RANK() OVER (PARTITION BY region ORDER BY amount DESC) = 1

-- 正确：用 CTE 包一层
WITH ranked AS (
    SELECT *, RANK() OVER (...) AS rnk FROM orders
)
SELECT * FROM ranked WHERE rnk = 1
```

**错误 3：混淆 RANK 和 ROW_NUMBER**
```sql
-- RANK：相同值并列，会跳号（1, 2, 2, 4）
-- ROW_NUMBER：强制不并列（1, 2, 3, 4）
-- 选哪个取决于业务需求
```

## 下一步建议

完成本课后，建议继续：
- **Polars 惰性流水线**：学习 Polars 的 lazy 模式，对比窗口函数在 Polars 中的写法（`over()`）
- 在 Playground 中尝试用窗口函数计算"每个品类的销售额占比"
