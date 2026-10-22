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
exercise:
  id: duckdb-joins-cte-amount-filter-v1
  title: 用 CTE 筛选高金额订单
  language: python
  starter_code: |
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
        # TODO: 用 CTE 先算出每笔订单的金额（quantity × unit_price），
        # 再筛出金额 > 250 的订单，输出 order_id 和 amount，按金额降序
    """).fetchall()

    print(result)
  objective: |
    用 WITH 定义 CTE 完成 LEFT JOIN 与金额计算，
    外层查询用 WHERE 过滤金额 > 250 的订单并降序排列。
  hints:
    - WITH order_amounts AS (SELECT ...) 先算每单金额
    - LEFT JOIN products p USING (product_id)
    - 外层 WHERE amount > 250 ORDER BY amount DESC
  validator:
    type: stdout_exact
    expected: "[(102, 899), (103, 360)]"
# 改版 M1：多 cell 工作区（重放式，严格顺序）
workspace:
  datasets:
    - ecommerce/orders.csv
    - ecommerce/products.csv
    - ecommerce/customers.csv
  cells:
    - id: c1
      kind: starter
      code: |
        import duckdb

        con = duckdb.connect()
        for name in ["orders", "products", "customers"]:
            con.execute(
                f"CREATE OR REPLACE TABLE {name} AS "
                f"SELECT * FROM read_csv_auto('data/ecommerce/{name}.csv')"
            )
            print(name, con.sql(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        print(con.sql("SELECT * FROM orders LIMIT 3").pl())
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: 用 LEFT JOIN 把 orders 和 products 连起来补出 category 列，
        # 只保留 order_id / product_id / category / amount 四列，存进 order_detail
        order_detail = con.sql("SELECT order_id, product_id, amount FROM orders LIMIT 5").pl()
        print(order_detail)
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 用 WITH 先算每笔订单的 revenue 与 profit（amount - cost * quantity），
        # 再按 category 汇总，按 revenue 降序，存进 category_stats
        category_stats = order_detail
        print(category_stats)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 先往 orders 里补一条 products 中不存在的模拟订单（P9999），
        # 再分别用 LEFT JOIN 与 INNER JOIN 统计行数拼成 join_compare，
        # 最后找出没有匹配到商品的订单存进 unmatched_orders
        join_compare = con.sql(
            "SELECT 'left' AS join_type, COUNT(*) AS row_count FROM orders"
        ).pl()
        unmatched_orders = con.sql("SELECT * FROM orders LIMIT 1").pl()
        print(join_compare)
        print(unmatched_orders)
  tasks:
    - id: t1
      title: 用 LEFT JOIN 补出商品品类
      cell: c2
      objective: |
        以 orders 为主表 LEFT JOIN products，用 product_id 关联，补出 category 列；
        结果只保留 order_id / product_id / category / amount 四列，存进 order_detail（.pl()）。
      assertions:
        - id: t1-schema
          type: schema
          title: order_detail 含四列
          var: order_detail
          columns: [order_id, product_id, category, amount]
        - id: t1-rows
          type: expr_true
          title: 行数不变，仍是 5000 行
          expr: "order_detail.height == 5000"
        - id: t1-total
          type: expr_true
          title: 金额合计 5287843.86
          expr: "abs(order_detail['amount'].sum() - 5287843.86) < 0.05"
        - id: t1-category
          type: expr_true
          title: category 没有空值
          expr: "order_detail['category'].null_count() == 0"
    - id: t2
      title: 用 CTE 先算派生指标再分组
      cell: c3
      objective: |
        用 WITH 算出每笔订单的 profit = amount - cost * quantity，
        再按 category 汇总 revenue（SUM(amount)）与 profit（SUM(profit)），按 revenue 降序，
        存进 category_stats（.pl()），共 5 行。
      assertions:
        - id: t2-schema
          type: schema
          title: category_stats 含 category / revenue / profit
          var: category_stats
          columns: [category, revenue, profit]
        - id: t2-rows
          type: expr_true
          title: 五个品类各一行
          expr: "category_stats.height == 5"
        - id: t2-total
          type: expr_true
          title: 五个品类 revenue 合计 5287843.86
          expr: "abs(category_stats['revenue'].sum() - 5287843.86) < 0.05"
        - id: t2-profit
          type: expr_true
          title: 数码品类 profit 为 979431.41
          expr: "abs(category_stats['profit'][category_stats['category'].to_list().index('数码')] - 979431.41) < 0.5"
    - id: t3
      title: 对比 LEFT JOIN 与 INNER JOIN 的行数差
      cell: c4
      objective: |
        先往 orders 追加一条 products 中不存在的订单（order_id 为 O999999、product_id 为 P9999），
        再用 UNION ALL 拼出 join_compare（join_type / row_count，含 left 与 inner 两行），
        并把没有匹配到商品的订单存进 unmatched_orders。
      assertions:
        - id: t3-schema
          type: schema
          title: join_compare 含 join_type / row_count
          var: join_compare
          columns: [join_type, row_count]
        - id: t3-left
          type: expr_true
          title: LEFT JOIN 是 5001 行
          expr: "join_compare['row_count'][join_compare['join_type'].to_list().index('left')] == 5001"
        - id: t3-inner
          type: expr_true
          title: INNER JOIN 是 5000 行
          expr: "join_compare['row_count'][join_compare['join_type'].to_list().index('inner')] == 5000"
        - id: t3-unmatched
          type: expr_true
          title: 恰好一条未匹配订单 P9999
          expr: "unmatched_orders.height == 1 and unmatched_orders['product_id'][0] == 'P9999'"
---

# DuckDB JOIN 与 CTE

## 这节课解决什么问题

前两课里你只动过一张 `orders` 表。但订单里只有 `product_id`、没有品类，只有 `customer_id`、没有客户分层——
想知道"哪个品类最赚钱"、"哪类客户消费最多"，就必须把订单表和商品表、客户表连接起来。

连接之后计算又变复杂了：金额要减成本算利润，利润要按品类汇总，汇总前还得过滤。一条 SQL 写下来容易长出七八层嵌套。

这一课给你两件工具，正好对应这两个困难：**`JOIN`** 把分散在多张表里的字段拼到一行里，
**`CTE`（`WITH ... AS`）** 把长查询拆成有名字的中间步骤，每一步只做一件事。

## 你将用到的数据

三张表都在 `data/ecommerce/` 下：`orders.csv`（5000 行，事实表）、`products.csv`（120 行）、`customers.csv`（800 行）。

| 表 | 关键列 | 说明 |
|----|--------|------|
| `orders` | `order_id`、`customer_id`、`product_id`、`quantity`、`amount`、`refunded` | 事实表；`amount` 是**折后成交价** |
| `products` | `product_id`、`category`、`unit_price`、`cost`、`launch_date` | 维度表；`category` 共 5 类，`cost` 是成本价 |
| `customers` | `customer_id`、`name`、`city`、`region`、`segment` | 维度表；`segment` 是新客 / 活跃 / 高价值 / 沉睡 |

规模与已知坑：

- 订单金额合计 5,287,843.86。`orders.amount` 是成交价，`products.unit_price` 是**标价**，两者不能混用。
  算成本要用 `products.cost * orders.quantity`，不是 `cost * amount`。
- 这份数据里 120 个商品**覆盖了全部 5000 条订单**，所以 `JOIN` 和 `LEFT JOIN` 的行数完全一样。
  想看到差异，必须自己补一条 `product_id` 不在商品表里的订单——这正是任务 `t3` 要做的。
- `product_id` 是文本列（`P0001`），不是整数，写条件时记得加引号。
- 品类一共 5 个，收入合计恰好等于订单总额；算出来对不上，通常是 JOIN 丢了行或重复了行。

## 核心概念

CTE 是 Common Table Expression 的缩写，写法是 `WITH name AS (...)`。它可以把复杂 SQL 拆成多个有名字的中间步骤，让查询更像一条分析流程。

`JOIN` 常用于把事实表和维度表合并：订单表记录"谁在什么时候买了什么"，商品表补充"属于哪个品类、成本是多少"，用户表补充"来自哪个城市或渠道"。

## JOIN 类型速查

| JOIN 类型 | 说明 | 使用场景 |
|-----------|------|----------|
| `INNER JOIN` | 只保留两表都匹配的行 | 需要严格关联数据时 |
| `LEFT JOIN` | 保留左表全部，右表匹配不上填 NULL | 以事实表为主，不能丢行时 |
| `CROSS JOIN` | 笛卡尔积，每行配每行 | 生成组合矩阵时 |

## 匹配与未匹配：JOIN 的真正区别

两者的差别只在**匹配不上的行**：`INNER JOIN` 直接丢弃，`LEFT JOIN` 保留并把右表列填 `NULL`。

所以"有多少行连不上"这件事，用 `LEFT JOIN` 之后数 `NULL` 最直接：

```sql
SELECT COUNT(*) FROM orders o
LEFT JOIN products p USING (product_id)
WHERE p.product_id IS NULL
```

`WHERE p.product_id IS NULL` 就是常说的 **anti join**，挑出"在右表找不到对应记录"的左表行。
反过来，两者行数相同就说明右表对每条左表记录都有匹配。

## 用 CTE 组织分析

CTE 里完成连接和字段计算，外层只负责聚合——不写 CTE 的话，你要么嵌套子查询，要么在 `GROUP BY` 里重写一遍表达式。

```python:example
import duckdb

con = duckdb.connect()
con.execute("CREATE TABLE orders AS SELECT * FROM (VALUES (101, 1, 2), (102, 2, 1), (103, 1, 3), (104, 3, 4)) AS t(order_id, product_id, quantity)")
con.execute("CREATE TABLE products AS SELECT * FROM (VALUES (1, '办公', 120), (2, '数码', 899), (3, '配件', 59)) AS t(product_id, category, unit_price)")

result = con.execute("""
    WITH order_detail AS (
        SELECT o.order_id, p.category, o.quantity * p.unit_price AS amount
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

判断标准很简单：**每当你发现自己在 `GROUP BY` 里重写一遍刚才算过的表达式，就该拆 CTE 了。**
每个 CTE 只做一件事——清洗、补字段、算指标或汇总。

## 任务清单

右边的**工作区**按顺序执行 `c1` → `c4`，共享同一个命名空间；`c1` 会把三张 CSV 建成 `orders` / `products` / `customers` 三张表。

| 任务 | 格子 | 交付物 | 验收标准 |
|------|------|--------|----------|
| `t1` 用 LEFT JOIN 补出商品品类 | `c2` | `order_detail` | 含 `order_id` / `product_id` / `category` / `amount`；5000 行；金额合计 5287843.86；`category` 无空值 |
| `t2` 用 CTE 先算派生指标再分组 | `c3` | `category_stats` | 含 `category` / `revenue` / `profit`；5 行；revenue 合计 5287843.86；数码 profit 为 979431.41 |
| `t3` 对比 LEFT JOIN 与 INNER JOIN | `c4` | `join_compare`、`unmatched_orders` | `join_compare` 含 `join_type` / `row_count`，left=5001、inner=5000；`unmatched_orders` 恰好 1 行且 `product_id` 是 `P9999` |

几点提醒：

1. `t1` 只做连接和选列，**不要**聚合；`amount` 直接用 `orders.amount`，别用 `unit_price` 重算。
2. `t2` 的 `profit` 先在 CTE 里算出来（`amount - cost * quantity`），外层只做 `SUM`。
3. `t3` 要改动 `orders` 表。建议用 `CREATE OR REPLACE TABLE orders AS (...) UNION ALL SELECT <模拟订单>` 追加，每次重跑都从干净状态开始。

## 常见错误

**错误 1：JOIN 后忘记去重或聚合**

JOIN 可能产生重复行，直接 `COUNT(*)` 会偏大。先想清楚你要数的是"订单数"还是"订单 × 商品组合数"，再决定要不要先去重或聚合。

**错误 2：混淆 WHERE 和 ON 的过滤时机**

`ON` 里的条件在 JOIN 时生效（影响是否匹配），`WHERE` 里的条件在 JOIN 之后生效（影响最终结果）。
在 `LEFT JOIN ... ON o.product_id = p.product_id AND p.category = '办公'` 里加过滤，右表不只产生 NULL 行，还会把不匹配的行整条筛掉。

**错误 3：把 anti join 写成 `WHERE category IS NULL`**

`category` 为空的成因可能有很多（数据缺失、连接错表）。判断"没连上"要用**右表主键** `p.product_id IS NULL`，这是唯一可靠的口径。

## 自检清单

- [ ] `order_detail` 是 5000 行、四列齐全，`category` 全非空、合计 5,287,843.86
- [ ] `category_stats` 是 5 行、按 revenue 降序，五个品类合计仍等于 5,287,843.86
- [ ] 数码的 `profit` ≈ 979,431.41（客单价高，利润明显高于其他品类）
- [ ] 追加模拟订单后 `LEFT JOIN` 是 5001 行、`INNER JOIN` 是 5000 行，未匹配的正是 `P9999`

## 下一步建议

- 学习 **窗口函数**：在不折叠行的情况下做组内计算
- 把 `customers` 也接进来：按 `segment` 汇总消费，看看哪类客户最值钱
- 尝试用 CTE 构建"订单明细 → 品类汇总 → 排名"的完整分析链
