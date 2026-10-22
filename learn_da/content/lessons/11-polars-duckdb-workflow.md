---
id: 11
slug: polars-duckdb-workflow
title: Polars 与 DuckDB 组合工作流
category: combined
difficulty: advanced
estimated_minutes: 45
order: 11
tags: [polars, duckdb, workflow, 实战, integration]
prev_lesson:
  slug: polars-lazy-pipeline
  title: Polars 惰性流水线
practice_objective: >-
  掌握 Polars 清洗 + DuckDB SQL 分析的组合工作流，
  能独立完成"数据清洗 → 注册到 DuckDB → SQL 汇总分析"的完整链路。
completion_criteria:
  - 用 Polars 完成缺失值填充和条件派生列
  - 用 to_arrow() + con.register() 将 Polars DataFrame 注册到 DuckDB
  - 用 DuckDB SQL 对清洗后的数据做分组聚合
  - 整个流程可在一个脚本中顺序执行
# Phase 3: 建议系统元数据
track: combined_workflow
prerequisites: [polars-basics, duckdb-analytics, polars-lazy-pipeline]
recommended_next: []
skill_tags: [polars_duckdb_integration, data_pipeline, arrow, workflow]
is_review_friendly: false
is_branch_point: false
exercise:
  id: polars-duckdb-clean-then-sql-v1
  title: Polars 清洗后交给 DuckDB 汇总
  language: python
  starter_code: |
    import duckdb
    import polars as pl

    orders = pl.DataFrame({
        "order_id": [1, 2, 3, 4, 5, 6],
        "region": ["华东", "华东", "华南", "华南", "华北", None],
        "category": ["办公", "数码", "办公", "配件", "办公", "数码"],
        "amount": [120, 899, 240, 59, 180, 620],
    })

    # TODO: 先用 Polars 把缺失的 region 填为"未知"，
    # 再用 to_arrow() + con.register() 注册到 DuckDB，
    # 最后用 SQL 按 region 汇总总金额并降序排列
    clean_orders = orders

    con = duckdb.connect()
    result = con.execute("""
    """).fetchall()

    print(result)
  objective: |
    完成“Polars 清洗 → 注册到 DuckDB → SQL 分组汇总”的完整链路：
    填充缺失区域后注册，用 GROUP BY + SUM 汇总并按总金额降序。
  hints:
    - pl.col('region').fill_null('未知') 先清洗再交给 SQL
    - con.register('orders', clean_orders.to_arrow())
    - SELECT region, SUM(amount) AS total_amount ... GROUP BY region ORDER BY total_amount DESC
  validator:
    type: stdout_exact
    expected: "[('华东', 1019), ('未知', 620), ('华南', 299), ('华北', 180)]"
# 改版 M4：多 cell 工作区（重放式，严格顺序）
workspace:
  datasets:
    - ecommerce/orders.csv
    - ecommerce/products.csv
  cells:
    - id: c1
      kind: starter
      code: |
        import duckdb
        import polars as pl

        orders = pl.read_csv("data/ecommerce/orders.csv")
        products = pl.read_csv("data/ecommerce/products.csv")
        print(orders.shape)
        print(orders.head(3))
        print(products.head(3))
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: ① 按 product_id 把 products 的 category 左连接进 orders
        #       ② 派生 net_amount：refunded 为 True 记 0.0，否则取 amount
        # 结果变量必须叫 orders_clean，行数保持 5000
        orders_clean = orders
        print(orders_clean.head(3))
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 用 orders_clean.to_arrow() 得到 arrow_table，
        # 再 con.register('orders_clean', arrow_table) 注册进 DuckDB，
        # 最后用 SQL 查出行数存进 registered_rows
        arrow_table = None
        con = duckdb.connect()
        registered_rows = 0
        print(registered_rows)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 用 DuckDB SQL 按 category 汇总 revenue（net_amount 求和）与 orders（订单数），
        # 用 con.sql(...).pl() 取回 Polars DataFrame，按 revenue 降序，变量叫 category_stats
        category_stats = orders_clean
        print(category_stats.head(3))
  tasks:
    - id: t1
      title: 用 Polars 补全品类并计算净额
      cell: c2
      objective: |
        按 product_id 把 products 的 category 左连接进 orders，并派生 net_amount 列，
        refunded 为 True 的订单记 0.0、其余取 amount。
        结果 DataFrame 必须叫 orders_clean，行数不变（5000），category 不能有空值。
      assertions:
        - id: t1-schema
          type: schema
          title: 结果包含 order_id / product_id / region / category / net_amount
          var: orders_clean
          columns: [order_id, product_id, region, category, net_amount]
        - id: t1-rows
          type: expr_true
          title: 连接不丢行，仍是 5000 行
          expr: "orders_clean.height == orders.height"
        - id: t1-category
          type: expr_true
          title: category 由 products 补全，无空值且恰好 5 个品类
          expr: "orders_clean['category'].null_count() == 0 and len(orders_clean['category'].unique()) == 5"
        - id: t1-refund
          type: expr_true
          title: 已退款订单的 net_amount 合计为 0
          expr: "orders_clean.filter(pl.col('refunded'))['net_amount'].sum() == 0"
    - id: t2
      title: 把清洗结果注册进 DuckDB
      cell: c3
      objective: |
        用 orders_clean.to_arrow() 得到 arrow_table，duckdb.connect() 之后
        用 con.register('orders_clean', arrow_table) 注册，表名必须是 orders_clean；
        registered_rows 存放 SQL 查到的行数，应等于 5000。
      assertions:
        - id: t2-arrow
          type: expr_true
          title: arrow_table 里有 net_amount 列
          expr: "arrow_table is not None and 'net_amount' in arrow_table.column_names"
        - id: t2-arrow-rows
          type: expr_true
          title: arrow_table 行数与 orders_clean 一致
          expr: "arrow_table is not None and arrow_table.num_rows == orders_clean.height"
        - id: t2-register
          type: expr_true
          title: registered_rows 来自 DuckDB 的行数查询，等于 5000
          expr: "registered_rows == orders_clean.height"
    - id: t3
      title: 用 DuckDB SQL 按品类汇总
      cell: c4
      objective: |
        用 DuckDB SQL 对 orders_clean 做 GROUP BY category，产出 revenue（net_amount 之和）
        与 orders（订单数）两列，并按 revenue 降序；
        用 con.sql(...).pl() 取回 Polars DataFrame，变量叫 category_stats。
      assertions:
        - id: t3-schema
          type: schema
          title: 结果包含 category / revenue / orders
          var: category_stats
          columns: [category, revenue, orders]
        - id: t3-rows
          type: expr_true
          title: 5 个品类各一行
          expr: "category_stats.height == 5"
        - id: t3-sorted
          type: expr_true
          title: 结果按 revenue 降序
          expr: "category_stats['revenue'].to_list() == sorted(category_stats['revenue'].to_list(), reverse=True)"
        - id: t3-total
          type: expr_true
          title: revenue 总和等于全部订单净额之和
          expr: "abs(category_stats['revenue'].sum() - orders_clean['net_amount'].sum()) < 1e-3"
---

# Polars 与 DuckDB 组合工作流

## 这节课解决什么问题

真实项目里，清洗和分析通常不是一种表达最顺手：清洗要逐列派生、补全、过滤，写成 SQL 又长又难读；而分组、排名、多表连接，写 SQL 又比一串 Polars 表达式直观得多。

这节课用 `orders.csv` 走一遍完整链路：先用 Polars 把订单表和商品表拼起来，算出「退款不算收入」之后的净额；再把清洗结果注册进 DuckDB；最后用一条 `GROUP BY` 拿到品类收入榜。

最终你会留下三个可重放的中间结果——`orders_clean`（干净明细）、`arrow_table` + `con`（DuckDB 里的表）、`category_stats`（品类汇总）。这三个变量就是本课的交付物。

## 你将用到的数据

`data/ecommerce/orders.csv`（5000 行）：

| 列名 | 类型 | 含义 |
|---|---|---|
| `order_id` | str | 订单号，`O000001` 起唯一 |
| `product_id` | str | 关联 `products.csv` |
| `region` | str | 华东 / 华北 / 华南 / 西南 |
| `quantity` | int | 件数，1-5 |
| `unit_price` | float | 下单时单价快照 |
| `discount` | float | 0.8 / 0.85 / 0.9 / 1.0 |
| `amount` | float | `round(unit_price * quantity * discount, 2)` |
| `refunded` | bool | 是否已退款，约 4% |

`data/ecommerce/products.csv`（120 行）：`product_id`、`category`（数码/家居/服饰/图书/食品）、`unit_price`、`cost`、`launch_date`。

已知坑：

- `orders.csv` **没有** `category` 列，品类只能从 `products.csv` 关联进来，所以第一步一定是 `join`，不是 `with_columns` 硬编码。
- `refunded` 是布尔列，`amount` 是下单金额、**不等于收入**：本课用 `net_amount` 表示退款后的净额，退款单按 0 计。
- `order_date` 读进来是字符串（`"2025-01-01"`），本课用不到日期；需要时先 `.str.to_date("%Y-%m-%d")`。`products.csv` 也有 `unit_price`，和 `orders.csv` 同名，join 前先 `select` 只带 `product_id` 和 `category`。

## Polars → DuckDB 桥梁

关键两行代码：

```python
# 1. 把 Polars DataFrame 转成 Arrow 格式
arrow_table = df.to_arrow()

# 2. 注册到 DuckDB 连接中，之后可以用 SQL 查询
con.register('my_table', arrow_table)
```

`register` 是**零拷贝**的：DuckDB 直接读 Arrow 的内存布局，所以几万行数据注册几乎是瞬间完成的。它注册的是那一刻的快照——之后再改 DataFrame，SQL 里看不到。

## 从清洗到 SQL 分析

```python
import duckdb
import polars as pl

small_orders = pl.DataFrame({
    "region": ["华东", "华东", "华南", "华南", "华北", None],
    "amount": [120, 899, 240, 59, 180, 620],
})

# 第 1 步：Polars 清洗 —— 填充缺失值 + 派生列
clean_orders = small_orders.with_columns(
    pl.col("region").fill_null("未知"),
    pl.when(pl.col("amount") >= 500).then(pl.lit("大额")).otherwise(pl.lit("普通")).alias("band"),
)

# 第 2 步：注册给 DuckDB（零拷贝，注册完就能用 SQL 查）
con = duckdb.connect()
con.register("orders", clean_orders.to_arrow())

# 第 3 步：SQL 汇总 —— CTE 算分组小计，窗口函数再排名
result = con.sql("""
    WITH s AS (
        SELECT region, band, COUNT(*) AS cnt, SUM(amount) AS total
        FROM orders GROUP BY region, band
    )
    SELECT *, RANK() OVER (ORDER BY total DESC) AS amount_rank FROM s ORDER BY amount_rank
""").fetchall()
print(result)
```

这段示例故意只用 6 行小数据，演示的是**动作顺序**（清洗 → 注册 → SQL），不是本课任务的答案：任务里是 5000 行真实订单，还多一步「从商品表带品类进来」。

## 工作流建议

一个清晰的组合流程通常包括：

1. 数据进入 Polars，先统一类型、处理缺失值
2. 用 Polars 表达式生成业务字段（净额、分档、拼接键）
3. 将处理后的表注册给 DuckDB
4. 用 SQL 写汇总、排名、分层分析
5. 回到 Polars 或 Python 中继续展示结果

判断标准很简单：**需要逐行改值、改类型、造列 → Polars；需要分组、连接、排名、窗口 → SQL**。

## 任务清单

右边工作区按 `c1 → c4` 顺序执行，**通过一道才解锁下一道**；改了前面的格，后面的格会退回「待复核」。`c1` 已经把两张表读进 `orders` / `products`，后面的格直接复用。

**t1 用 Polars 补全品类并计算净额**（变量 `orders_clean`）

- 按 `product_id` 把 `products` 的 `category` 左连接进 `orders`，行数必须仍是 5000；
- 派生 `net_amount`：`refunded` 为 True 记 `0.0`，其余取 `amount`；
- `category` 不能有空值，5 个品类都要出现。

**t2 把清洗结果注册进 DuckDB**（变量 `arrow_table` / `con` / `registered_rows`）

- `arrow_table = orders_clean.to_arrow()`；
- `con = duckdb.connect()` 后 `con.register('orders_clean', arrow_table)`，**表名必须是 `orders_clean`**；
- 用 `SELECT COUNT(*) FROM orders_clean` 把行数存进 `registered_rows`，应等于 5000。

**t3 用 DuckDB SQL 按品类汇总**（变量 `category_stats`）

- SQL 里 `GROUP BY category`，聚合出 `SUM(net_amount) AS revenue` 与 `COUNT(*) AS orders`；
- `ORDER BY revenue DESC`；
- 用 `con.sql("...").pl()` 取回 Polars DataFrame，变量叫 `category_stats`，`revenue` 总和应等于全部净额之和。

> 断言直接引用 `orders_clean`、`arrow_table`、`con`、`category_stats` 这四个名字，改名会判不通过。

## 常见错误

**错误 1：忘记注册就直接查询**
```python
con.execute("SELECT * FROM df")                     # 错：DuckDB 不知道 df 是什么
con.register("df", df.to_arrow())                   # 对：先注册再查
con.execute("SELECT * FROM df")
```

**错误 2：把 Polars 语法写进 SQL** —— `pl.col('amount')` 是 Python 表达式，SQL 里只能写列名 `amount`。

**错误 3：清洗不充分就交给 SQL** —— 缺失值、脏字符串要在 Polars 阶段处理完，否则 SQL 里会冒出意外 NULL。

**错误 4：把退款单也算进收入** —— `SUM(amount)` 把已经退回去的钱也算成收入；正确做法是先派生 `net_amount`（退款单为 0），SQL 只汇总 `net_amount`。

**错误 5：register 之后再改 `orders_clean`**
```python
con.register("orders_clean", orders_clean.to_arrow())
orders_clean = orders_clean.filter(pl.col("region") == "华东")   # SQL 里看不到这次过滤
# 注册的是快照：要改就改完再注册
```

## 自检清单

- [ ] `orders_clean` 是 5000 行，且同时有 `category` 与 `net_amount` 两列
- [ ] 退款订单的 `net_amount` 合计为 0（不是「约等于」）
- [ ] `category_stats` 是 5 行、按 `revenue` 降序，且 `revenue` 总和等于全部净额之和
- [ ] 能用自己的话说清：哪些活留给 Polars，哪些活交给 SQL

## 下一步建议

- 尝试用这个工作流处理你自己的数据（CSV 文件 → Polars 读取 → 清洗 → DuckDB 分析）
- 在 t3 的 SQL 里加一个 `RANK() OVER (ORDER BY revenue DESC)`，把品类收入排名也带出来
