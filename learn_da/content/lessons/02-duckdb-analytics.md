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
workspace:
  datasets:
    - ecommerce/orders.csv
  cells:
    - id: c1
      kind: starter
      code: |
        import duckdb

        con = duckdb.connect()
        # 先看看这份 CSV 有哪些列、前几行长什么样
        print(con.sql("DESCRIBE SELECT * FROM read_csv_auto('data/ecommerce/orders.csv')").pl())
        print(con.sql("SELECT * FROM read_csv_auto('data/ecommerce/orders.csv') LIMIT 3").pl())
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: 把 CSV 变成可复用的 orders 表（CREATE TABLE AS 或 con.register），
        # 再把完整明细取成 orders_df（用 .pl()），行数存进 order_count
        orders_df = con.sql(
            "SELECT * FROM read_csv_auto('data/ecommerce/orders.csv') LIMIT 3"
        ).pl()
        order_count = 0
        print(order_count)
        print(orders_df)
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 用 GROUP BY region 汇总 revenue（SUM(amount)）与 orders（COUNT(*)），
        # 按 revenue 降序，结果用 .pl() 存进 region_stats
        region_stats = orders_df
        print(region_stats)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 按 amount 降序取金额最大的 5 笔订单，只保留 order_id 和 amount，
        # 结果用 .pl() 存进 top_orders
        top_orders = orders_df.head(5)
        print(top_orders)
  tasks:
    - id: t1
      title: 把订单 CSV 读成可复用的表
      cell: c2
      objective: |
        用 duckdb.connect() 建连接，用 read_csv_auto('data/ecommerce/orders.csv')
        配合 CREATE TABLE AS（或 con.register）把订单数据读进名为 orders 的表；
        再把完整明细取成 Polars DataFrame orders_df，行数存进 order_count。
      assertions:
        - id: t1-schema
          type: schema
          title: 明细包含订单的关键列
          var: orders_df
          columns: [order_id, customer_id, product_id, region, channel, amount, refunded]
        - id: t1-rows
          type: expr_true
          title: order_count 等于订单总行数 5000
          expr: "order_count == 5000"
        - id: t1-unique
          type: expr_true
          title: order_id 有 5000 个不重复值（没读丢、也没读重）
          expr: "orders_df['order_id'].n_unique() == 5000"
    - id: t2
      title: 按区域汇总 revenue 与订单数
      cell: c3
      objective: |
        用 GROUP BY region 汇总每个区域的 revenue（SUM(amount)）与 orders（COUNT(*)），
        按 revenue 降序排列，结果用 .pl() 存进 region_stats；数据来自 orders 表。
      assertions:
        - id: t2-schema
          type: schema
          title: region_stats 含 region / revenue / orders
          var: region_stats
          columns: [region, revenue, orders]
        - id: t2-exact
          type: frame_equal
          title: 四个区域的订单数与金额与参考结果逐行一致
          var: region_stats
          ref: 02-t2-region-stats.parquet
          order_matters: true
          rtol: 1e-6
    - id: t3
      title: 按金额取 Top 5 订单
      cell: c4
      objective: |
        用 ORDER BY amount DESC + LIMIT 5 取金额最大的 5 笔订单，只保留 order_id 与
        amount 两列，结果用 .pl() 存进 top_orders（金额并列时顺序不唯一，别按 order_id 硬编码）。
      assertions:
        - id: t3-schema
          type: schema
          title: top_orders 只含 order_id / amount 两列
          var: top_orders
          columns: [order_id, amount]
          exact: true
        - id: t3-exact
          type: frame_equal
          title: 五行订单与参考结果一致（金额并列时顺序不限）
          var: top_orders
          ref: 02-t3-top-orders.parquet
          order_matters: false
          rtol: 1e-6
---

# DuckDB 查询分析

## 这节课解决什么问题

你已经会用 Polars 处理 DataFrame 了，但有一大类问题用 SQL 表达更自然：**"按区域汇总收入"、"按渠道数订单"、"取金额最大的 5 笔"。**

仓库里的 `orders.csv` 有 5000 条订单、合计 528 万收入，分散在四个区域、四个渠道。运营每周都要看这几张汇总表。
这一课让你第一次把这份真实数据装进 DuckDB，用 SQL 把明细变成汇总：建连接 → 读 CSV 成表 → `GROUP BY` 汇总 → `ORDER BY` 排序。

## 什么是 DuckDB？

DuckDB 是一个嵌入式分析数据库，专为 OLAP 工作负载设计。它可以直接在 Python 进程中运行，无需安装服务器。

- **零配置** - 无需安装服务器，`pip install duckdb` 即可使用
- **高性能** - 列式存储，向量化执行
- **SQL 兼容** - 支持标准 SQL 语法

## 你将用到的数据

文件：`data/ecommerce/orders.csv`（5000 行、11 列）。本课重点用下面这些列：

| 列名 | 类型 | 含义 |
|------|------|------|
| `order_id` | 文本 | 唯一订单号，`O000001` 起 |
| `region` | 文本 | 收货区域：华东 / 华北 / 华南 / 西南 |
| `channel` | 文本 | 下单渠道：app / web / mini_program / offline |
| `quantity` / `unit_price` / `discount` | 整数 / 小数 | 件数、单价快照、折扣率 |
| `amount` | 小数 | **折后金额** = `round(unit_price * quantity * discount, 2)` |
| `order_date` | 日期 | 2025-01-01 ~ 2025-12-31 |
| `refunded` | 布尔 | 约 4% 的订单已退款（206 条） |

规模与已知坑：

- 5000 行、`amount` 合计 **5,287,843.86**；四个区域各 1181 ~ 1308 单，单量并不均衡。
- `read_csv_auto()` 会自动推断类型：`order_date` → `DATE`、`refunded` → `BOOLEAN`，不需要手工转换。
- `amount` 已经是折后金额，**不要**再乘 `discount`，否则整体偏高。

## 核心概念：连接、建表与聚合

```python
import duckdb

con = duckdb.connect()  # 内存数据库，关闭连接后数据消失

con.execute(
    "CREATE TABLE orders AS SELECT * FROM read_csv_auto('data/ecommerce/orders.csv')"
)

print(con.sql("""
    SELECT
        region,
        COUNT(*) AS order_count,
        SUM(amount) AS total_amount
    FROM orders
    GROUP BY region
    ORDER BY total_amount DESC
""").fetchall())
```

`CREATE TABLE ... AS SELECT` 一行就把 CSV 变成可反复查询的表；`GROUP BY` 后面的列必须和 `SELECT` 里的非聚合列一致；
聚合结果建议起别名（`total_amount` 比 `sum(amount)` 好读）。`con.sql(...)` 与 `con.execute(...)` 等价，但前者能直接接 `.pl()` 把结果转成 Polars。

## SQL → Polars 对照

| 操作 | Polars | SQL (DuckDB) |
|------|--------|-------------|
| 选择列 | `df.select(['a', 'b'])` | `SELECT a, b FROM t` |
| 筛选行 | `df.filter(pl.col('x') > 10)` | `WHERE x > 10` |
| 分组聚合 | `df.group_by('g').agg(pl.col('v').sum())` | `GROUP BY g` + `SUM(v)` |
| 排序 | `df.sort('v', descending=True)` | `ORDER BY v DESC` |
| 添加列 | `df.with_columns(...)` | `SELECT *, expr AS new_col` |

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

## 任务清单

右边的**工作区**按顺序执行 `c1` → `c4`，共享同一个命名空间；通过当前任务的断言才会解锁下一个。

| 任务 | 格子 | 交付物 | 验收标准 |
|------|------|--------|----------|
| `t1` 把订单 CSV 读成可复用的表 | `c2` | `orders_df`、`order_count` | 含 `order_id` / `customer_id` / `product_id` / `region` / `channel` / `amount` / `refunded`；`order_count == 5000`；`order_id` 不重复 |
| `t2` 按区域汇总 revenue 与订单数 | `c3` | `region_stats` | 含 `region` / `revenue` / `orders`；四个区域各一行；按 revenue 降序；**每行数值与服务端参考结果逐行一致**（不再只看行数与合计） |
| `t3` 按金额取 Top 5 订单 | `c4` | `top_orders` | 只有 `order_id` / `amount` 两列；恰好 5 行；**五行与参考结果一致**（金额并列时顺序不限） |

三点提醒：

1. `c1` 只是让你看见数据长什么样，建表要自己写；`con.register()` 和 `CREATE TABLE AS` 都可以，后者更常用。
2. 金额最大的前 5 笔里有**并列**（两笔 18298.95、两笔 17758.6），顺序不唯一，别按 `order_id` 硬编码。
3. 变量名必须是 `orders_df`、`order_count`、`region_stats`、`top_orders`，断言靠名字找结果。

## 常见坑

**错误 1：WHERE 和 HAVING 混淆**

`WHERE SUM(amount) > 200` 会直接报错——聚合值在分组之后才存在。过滤明细行用 `WHERE`，过滤分组结果用 `HAVING SUM(amount) > 200`。

**错误 2：GROUP BY 缺少非聚合列**

`SELECT region, channel, SUM(amount) ... GROUP BY region` 里的 `channel` 会取"任意一行"，结果不可靠；所有非聚合列都要写进 `GROUP BY`。

**错误 3：重复计算折扣**

`amount` 已经是折后金额。写 `SUM(unit_price * quantity * discount)` 看似更"原始"，实际会漏掉 CSV 里已做的取整，
合计与 5,287,843.86 对不上——汇总一律用 `amount`。

## 自检清单

- [ ] `order_count` 是 5000，`order_id` 没有重复值（没读丢也没读重）
- [ ] `region_stats` 是 4 行，`revenue` 合计 5,287,843.86，按 revenue 从大到小
- [ ] `top_orders` 是 5 行、最大金额 19236.8，且只含两列

## 下一步建议

- **Polars 分组聚合**：对比 Polars 的 `group_by` 和 SQL 的 `GROUP BY`，理解两种表达方式
- **DuckDB JOIN 与 CTE**：把 `products` / `customers` 接进来，按品类和客户分层汇总
- 在 Playground 中继续用 `con.register()` 把 Polars DataFrame 交给 DuckDB 查询
