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
workspace:
  datasets:
    - ecommerce/orders.csv
  cells:
    - id: c1
      kind: starter
      code: |
        import duckdb

        con = duckdb.connect()
        con.execute(
            "CREATE TABLE orders AS SELECT * FROM read_csv_auto('data/ecommerce/orders.csv')"
        )
        print(con.sql("SELECT COUNT(*) AS rows FROM orders").fetchall())
        print(con.sql("SELECT * FROM orders LIMIT 3").pl())
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: 用 WHERE 筛出「未退款（refunded = FALSE）且 amount >= 100」的订单，
        # 结果用 .pl() 存进 filtered_orders
        filtered_orders = con.sql("SELECT * FROM orders").pl()
        print(filtered_orders.height)
        print(filtered_orders.head(3))
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 按 channel 分组，汇总订单数 orders 与金额 revenue，
        # 按 revenue 降序，结果用 .pl() 存进 channel_stats
        channel_stats = filtered_orders
        print(channel_stats)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 在聚合的基础上加 HAVING，只保留订单数 >= 1260 的渠道，
        # 结果用 .pl() 存进 big_channels
        big_channels = channel_stats
        print(big_channels)
  tasks:
    - id: t1
      title: 用 WHERE 筛选未退款的高客单价订单
      cell: c2
      objective: |
        用 WHERE 同时筛两个条件：refunded = FALSE 且 amount >= 100，
        结果用 .pl() 存进 filtered_orders；只保留 order_id / amount / refunded
        三列（多留列会与参考结果的列数不一致），不要做聚合。
      assertions:
        - id: t1-schema
          type: schema
          title: filtered_orders 含 order_id / amount / refunded
          var: filtered_orders
          columns: [order_id, amount, refunded]
        - id: t1-exact
          type: frame_equal
          title: 筛选结果的每一行都与参考结果一致（3722 行）
          var: filtered_orders
          ref: 07-t1-filtered-orders.parquet
          order_matters: false
          rtol: 1e-6
    - id: t2
      title: 按渠道汇总订单数与金额
      cell: c3
      objective: |
        用 GROUP BY channel 汇总订单数 orders（COUNT(*)）与金额 revenue（SUM(amount)），
        按 revenue 降序，结果用 .pl() 存进 channel_stats；数据取自整张 orders 表。
      assertions:
        - id: t2-schema
          type: schema
          title: channel_stats 含 channel / orders / revenue
          var: channel_stats
          columns: [channel, orders, revenue]
        - id: t2-exact
          type: frame_equal
          title: 四个渠道的订单数与金额与参考结果逐行一致
          var: channel_stats
          ref: 07-t2-channels.parquet
          order_matters: true
          rtol: 1e-6
    - id: t3
      title: 用 HAVING 过滤订单量过千的渠道
      cell: c4
      objective: |
        在按 channel 聚合的基础上加 HAVING，只保留订单数 >= 1260 的渠道，
        结果用 .pl() 存进 big_channels，列与 channel_stats 保持一致。
      assertions:
        - id: t3-schema
          type: schema
          title: big_channels 含 channel / orders / revenue
          var: big_channels
          columns: [channel, orders, revenue]
        - id: t3-rows
          type: expr_true
          title: 只剩 2 个渠道
          expr: "big_channels.height == 2"
        - id: t3-channels
          type: expr_true
          title: 剩下的是 app 与 web
          expr: "sorted(big_channels['channel'].to_list()) == ['app', 'web']"
        - id: t3-threshold
          type: expr_true
          title: 每行订单数都 >= 1260
          expr: "all(int(n) >= 1260 for n in big_channels['orders'].to_list())"
---

# DuckDB SQL 分析基础

## 这节课解决什么问题

你已经能把 CSV 读进 DuckDB 了，接下来的问题是：**怎么从 5000 条明细里挑出想要的那部分，再按业务维度汇总？**

这份 `orders.csv` 里混着约 4% 的退款订单，也有大量几十块钱的小单。运营想知道：去掉退款、只看客单价 100 元以上的订单，各个渠道分别贡献了多少单、多少钱；其中真正"能扛量"的渠道又是哪几个。

这一课交付的就是这套基本功：`WHERE` 筛明细 → `GROUP BY` + 聚合算指标 → `HAVING` 过滤分组结果 → `ORDER BY` 排序——SQL 里出现频率最高的四个子句。

## 你将用到的数据

文件：`data/ecommerce/orders.csv`（5000 行、11 列），本课重点用下面这些列。

| 列名 | 类型 | 含义 |
|------|------|------|
| `order_id` | 文本 | 唯一订单号，`O000001` 起 |
| `channel` | 文本 | 下单渠道：app / web / mini_program / offline |
| `quantity` / `unit_price` / `discount` | 整数 / 小数 | 件数、单价快照、折扣率 |
| `amount` | 小数 | **折后金额**，筛选客单价直接用这一列 |
| `order_date` | 日期 | 2025-01-01 ~ 2025-12-31 |
| `refunded` | 布尔 | 约 4% 的订单已退款（206 条） |

规模与已知坑：

- 5000 行、合计 5,287,843.86；未退款 4794 条。
- `refunded` 是**布尔**列，写 `WHERE refunded = FALSE`（或 `WHERE NOT refunded`），别写成字符串 `'false'`。
- 四个渠道的单量都在 1200 上下（最大 1272、最小 1206），「单量过千」会把四个渠道全留下——阈值要设在 **1260** 这一档。

## 核心概念：子句的书写顺序 ≠ 执行顺序

| 书写顺序 | 子句 | 作用 | 逻辑执行顺序 |
|----------|------|------|--------------|
| 1 | `SELECT` | 选择或计算输出字段 | 5 |
| 2 | `FROM` | 指定数据来源 | 1 |
| 3 | `WHERE` | 过滤明细行（不能用聚合函数） | 2 |
| 4 | `GROUP BY` | 分组 | 3 |
| 5 | `HAVING` | 过滤分组结果（可以用聚合函数） | 4 |
| 6 | `ORDER BY` | 排序 | 6 |
| 7 | `LIMIT` | 取前 N 行 | 7 |

记住这条顺序，你就不会问「为什么 WHERE 里写 `SUM(amount) > 100` 会报错」——`WHERE` 在分组之前执行，那时聚合值还不存在；`AS` 别名同理 `WHERE` 里引用不到。

## 汇总订单数据

```python
import duckdb
con = duckdb.connect()

print(con.sql("""
    SELECT
        region,
        COUNT(*) AS order_count,
        SUM(amount) AS total_amount
    FROM read_csv_auto('data/ecommerce/orders.csv')
    WHERE amount >= 100
    GROUP BY region
    ORDER BY total_amount DESC
""").fetchall())
```

这段查询用到了本课的全部结构：`WHERE` 先筛掉小额订单，`GROUP BY` 把剩下的行按区域归类，聚合函数算出指标，最后 `ORDER BY` 排序。

## WHERE 与 HAVING 的分工

- `WHERE`：作用在**明细行**上，逐行判断，能用 `order_id`、`amount`、`refunded` 这些原始列。
- `HAVING`：作用在**分组结果**上，判断的是 `COUNT(*)`、`SUM(amount)` 这类聚合值。

两个条件都要时并不冲突：`WHERE` 先筛行，`HAVING` 再筛组，可以写进同一条查询：

```sql
SELECT channel, COUNT(*) AS orders FROM orders
WHERE refunded = FALSE
GROUP BY channel
HAVING COUNT(*) >= 1000
```

## 练习

**动作 1**：按 `category`（品类）统计订单数和总金额。**动作 2**：只保留总金额大于 200 的品类，并按总金额从高到低排序。

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

## 任务清单

右边的**工作区**按顺序执行 `c1` → `c4`，共享同一个命名空间。通过一个任务的断言才会解锁下一个。

| 任务 | 格子 | 交付物 | 验收标准 |
|------|------|--------|----------|
| `t1` 用 WHERE 筛未退款的高客单价订单 | `c2` | `filtered_orders` | 只含 `order_id` / `amount` / `refunded` 三列；**3722 行每一行都与参考结果一致**（多留列会判失败） |
| `t2` 按渠道汇总 | `c3` | `channel_stats` | 含 `channel` / `orders` / `revenue`；四个渠道各一行；按 revenue 降序；**每行与服务端参考结果逐行一致** |
| `t3` 用 HAVING 过滤订单量过千的渠道 | `c4` | `big_channels` | 列同 `channel_stats`；只剩 2 个渠道；是 app 与 web；每行订单数都 >= 1260 |

三点提醒：

1. `t1` 只筛行、不聚合；`t2` 才聚合，而且要在**整张** `orders` 表上聚合（不是只在 `filtered_orders` 上）。
2. `t3` 必须用 `HAVING`：写成 `WHERE COUNT(*) >= 1260` 会直接报错，这正是本课要你体会的区别。
3. 变量名必须是 `filtered_orders`、`channel_stats`、`big_channels`，断言靠名字找结果。

## 常见坑

**错误 1：在筛选后的结果上做渠道汇总**

`channel_stats` 要的是「全部订单按渠道汇总」。如果从 `filtered_orders` 出发，得到的是「未退款且金额 >= 100 的订单汇总」，合计只有 496 万而不是 528 万。

**错误 2：WHERE 里用聚合函数**

`WHERE SUM(amount) > 200` 会报错：聚合值在分组之后才存在，明细行阶段还没有它。过滤分组结果要用 `HAVING`。

**错误 3：布尔值写成字符串**

`refunded` 是 `BOOLEAN` 列，`WHERE refunded = 'false'` 与字符串比较恒为假、结果 0 行；正确写法是 `WHERE refunded = FALSE`。

## 自检清单

- [ ] `filtered_orders` 是 3722 行，`refunded` 全为假、`amount` 最小 100.26
- [ ] `channel_stats` 是 4 行、按 revenue 降序，`big_channels` 只剩 app 与 web（用了 `HAVING` 而不是 `WHERE`）
- [ ] `t2` 用的是整张 `orders` 表，不是 `filtered_orders`

## 下一步建议

- 学习 **JOIN 与 CTE**：把商品表、客户表连接进来做更复杂的分析（如 `order_date >= DATE '2025-07-01'` 这样的时间范围）
- 尝试在 DuckDB 中直接查询 Polars DataFrame（`con.register()`）
