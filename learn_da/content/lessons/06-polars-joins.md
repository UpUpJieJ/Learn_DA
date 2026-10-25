---
id: 6
slug: polars-joins
title: Polars 连接与合并
category: polars
difficulty: intermediate
estimated_minutes: 30
order: 6
tags: [polars, join, lookup, 数据建模]
prev_lesson:
  slug: polars-cleaning
  title: Polars 数据清洗
next_lesson:
  slug: duckdb-sql-foundations
  title: DuckDB SQL 分析基础
practice_objective: >-
  掌握 Polars 的 join 操作，能用 left join 补充维度字段、
  用 anti join 做数据质量检查。
completion_criteria:
  - 用 join + on + how="left" 连接两张表
  - 连接后用 with_columns 计算派生字段
  - 用 how="anti" 找出未匹配的记录
  - 理解 left / inner / outer / semi / anti 的区别
# Phase 3: 建议系统元数据
track: polars_basics
prerequisites: ['polars-basics', 'polars-cleaning']
recommended_next: ['duckdb-sql-foundations', 'polars-lazy-pipeline']
skill_tags: ['join', 'left_join', 'anti_join', 'data_modeling']
is_review_friendly: false
is_branch_point: true
workspace:
  datasets:
    - ecommerce/orders.csv
    - ecommerce/customers.csv
  cells:
    - id: c1
      kind: starter
      code: |
        import polars as pl

        orders = pl.read_csv("data/ecommerce/orders.csv")
        customers = pl.read_csv("data/ecommerce/customers.csv")
        print(orders.shape, customers.shape)
        print(orders.head(3))
        print(customers.head(3))
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: 用 how="left" 把 customers 的 segment 补到每一笔订单上，
        # 结果叫 orders_customers，行数必须还是 5000
        orders_customers = orders
        print(orders_customers.head(3))
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 先派生 net_amount（已退款订单记 0，其余取 amount），
        # 再按 segment 聚合 revenue 与订单数 orders，按 revenue 降序
        segment_stats = orders_customers
        print(segment_stats)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 用 how="anti" 找出 customer_id 在客户表里不存在的订单
        orphan_orders = orders
        print(orphan_orders.height)
  tasks:
    - id: t1
      title: 用 left join 补出客户分层
      cell: c2
      objective: |
        用 orders.join(customers, on="customer_id", how="left") 得到 orders_customers，
        必须保留全部 5000 行订单，并新增 segment 列（不能有 null）。
      assertions:
        - id: t1-schema
          type: schema
          title: 结果包含 order_id / customer_id / segment 三列
          var: orders_customers
          columns: [order_id, customer_id, segment]
        - id: t1-rows
          type: expr_true
          title: 5000 行订单一行都没丢（用的是 left 而不是 inner）
          expr: "orders_customers.height == 5000"
        - id: t1-segment
          type: expr_true
          title: 订单 O000001 的客户分层是 高价值
          expr: "orders_customers.filter(pl.col('order_id') == 'O000001')['segment'].to_list() == ['高价值']"
        - id: t1-null
          type: expr_true
          title: segment 没有空值（说明连接键对得上）
          expr: "orders_customers['segment'].null_count() == 0"
    - id: t2
      title: 派生净额并按客户分层聚合
      cell: c3
      objective: |
        在 orders_customers 上派生 net_amount（refunded 为 True 记 0，否则取 amount），
        再按 segment 聚合 revenue = net_amount 之和、orders = 订单数，按 revenue 降序，
        结果变量叫 segment_stats。
      assertions:
        - id: t2-schema
          type: schema
          title: 结果包含 segment / revenue / orders 三列
          var: segment_stats
          columns: [segment, revenue, orders]
        - id: t2-exact
          type: frame_equal
          title: 四个分层的净额与订单数与参考结果逐行一致
          var: segment_stats
          ref: 06-t2-segment-stats.parquet
          order_matters: true
          rtol: 1e-6
    - id: t3
      title: 反连接做数据质量检查
      cell: c4
      objective: |
        用 how="anti" 检查订单里的 customer_id 是否都能在 customers 中找到：
        orphan_orders = orders.join(customers, on="customer_id", how="anti")，
        结果应为 0 行，且列结构与 orders 完全一致。
      assertions:
        - id: t3-schema
          type: schema
          title: 结果保留 orders 的订单号与客户号
          var: orphan_orders
          columns: [order_id, customer_id]
        - id: t3-empty
          type: expr_true
          title: 孤儿订单数量为 0
          expr: "orphan_orders.height == 0"
        - id: t3-columns
          type: expr_true
          title: 列与 orders 一致（anti 只保留左表列）
          expr: "orphan_orders.columns == orders.columns"
---

# Polars 连接与合并

## 这节课解决什么问题

`orders.csv` 有 5000 笔订单，但每笔只记了 `customer_id`，看不出下单的人是谁、属于哪个客户分层；`segment`（新客 / 活跃 / 沉睡 / 高价值）只存在 `customers.csv` 里。业务方现在要回答两个问题：**每个客户分层贡献了多少净销售额**，以及**订单里的客户编号是不是都能在客户表里找到**（找不到就是脏数据，会影响后续归因和考核）。

这两件事正好对应 join 的两种用法：`how="left"` 把维度字段补进事实表，`how="anti"` 专门用来做数据质量检查。本课你要交付三样东西：一张 5000 行的订单宽表（带 `segment`）、一份按客户分层聚合的 `segment_stats`，以及一份反连接检查结果 `orphan_orders`。

## 你将用到的数据

`data/ecommerce/orders.csv`（5000 行，11 列，本课只用到下面几列）

| 字段 | 类型 | 含义 |
|---|---|---|
| `order_id` | str | `O000001` 形式的订单号，唯一 |
| `customer_id` | str | 关联客户表，`C000001` 形式 |
| `region` | str | 下单区域：华东 / 华北 / 华南 / 西南 |
| `amount` | float | 订单实付金额（已含数量与折扣） |
| `refunded` | bool | 是否已退款，约 4% |

`data/ecommerce/customers.csv`（800 行，6 列）：`customer_id`、`name`、`city`、`region`、`segment`、`signup_date`。

已知坑：

- 两张表都有 `region` 列。直接 join 后 Polars 会生成 `region_right`，别把「客户所在区域」和「下单区域」混用。
- 两张表的 `customer_id` 都是字符串。用整数去 join 一行都匹配不上，反连接还会把 5000 行全报成孤儿。
- `orders` 里只出现 799 个不同的 `customer_id`，客户表有 800 行：维表比事实表的键更全。所以本数据集里 `left` 和 `inner` 的行数恰好一样——那是数据干净，不是可以省略 `how` 的理由。

## Pandas → Polars 对照

| Pandas | Polars | 说明 |
|--------|--------|------|
| `df.merge(dim, on='id', how='left')` | `df.join(dim, on="id", how="left")` | 方法名不同 |
| `df.merge(dim, left_on='a', right_on='b')` | `df.join(dim, left_on="a", right_on="b")` | 不同列名连接 |
| `pd.concat([df1, df2])` | `pl.concat([df1, df2])` | 纵向拼接 |

## 常见连接类型

数据分析中经常需要把多张表合并：订单表记录交易，商品表记录品类和成本，客户表记录分层。连接可以把分散的信息组织成一张分析宽表。

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `left` | 保留左表所有记录 | 给事实表补充维度信息 |
| `inner` | 只保留两边都匹配的记录 | 需要严格关联数据 |
| `outer` | 保留两边所有记录 | 合并两个独立数据集 |
| `semi` | 保留左表中能匹配右表的记录 | 过滤出「有关联的」记录 |
| `anti` | 保留左表中不能匹配右表的记录 | 数据质量检查 |

## 在小数据上热身：`left` 与 `anti`

下面这份 5 行玩具数据用 `user_id`、`product_id` 关联两张维表，和右边工作区的数据集不是同一份；把四个动作写在同一个草稿格里练手。

```python:example
import polars as pl

orders = pl.DataFrame({
    "order_id": [101, 102, 103, 104, 105],
    "user_id": [1, 2, 1, 3, 99],
    "product_id": [1, 2, 1, 3, 2],
    "quantity": [2, 1, 5, 3, 1],
})
users = pl.DataFrame({"user_id": [1, 2, 3], "city": ["北京", "上海", "深圳"]})
products = pl.DataFrame({
    "product_id": [1, 2, 3],
    "category": ["办公", "数码", "配件"],
    "unit_price": [120, 899, 59],
})

# 动作 1+2：两次 left join 补城市、品类与单价，再派生金额
result = (
    orders
    .join(users, on="user_id", how="left")
    .join(products, on="product_id", how="left")
    .with_columns((pl.col("quantity") * pl.col("unit_price")).alias("amount"))
)
print(result)

# 动作 3：按城市统计总金额，找出消费最高的城市
print(
    result.group_by("city")
    .agg(pl.col("amount").sum().alias("total_amount"))
    .sort("total_amount", descending=True)
)

# 动作 4：anti join 找出 user_id 在用户表中不存在的订单（99 号）
print(orders.join(users, on="user_id", how="anti"))
```

注意两点：`join` 默认是 `inner`，分析中推荐显式写 `how="left"`，否则没有匹配的行会被悄悄丢掉；`anti` 只返回**左表的列**，所以结果可以直接和原表对比列结构，适合做数据质量检查。

## 连接前的三个检查

在真实项目里，join 之前值得先花 30 秒做三件事，能省掉后面半小时的排查：

1. **键是不是唯一**：`customers["customer_id"].is_unique()`。右表键重复会让左表一行变多行，行数悄悄翻倍。
2. **连接后行数对不对**：`left` 连接的行数应该等于左表行数。变多说明右表键重复，变少说明你其实写成了 `inner`。
3. **连接后有没有空值**：`df["segment"].null_count()`。空值就是「匹配不上的记录」，正好是下一步 `anti` 要检查的对象。
## 任务清单

右边工作区按 `c1 → c2 → c3 → c4` 顺序执行，**当前任务通过后才解锁下一个**；改了前面的格，后面的格会变成待重跑。

| 任务 | 单元格 | 要交付的变量 | 验收标准 |
|---|---|---|---|
| `t1` 用 left join 补出客户分层 | `c2` | `orders_customers` | 保留 5000 行、新增 `segment` 且无空值、订单 `O000001` 的分层为「高价值」 |
| `t2` 派生净额并按分层聚合 | `c3` | `segment_stats` | 派生 `net_amount`（退款记 0）、四个分层各一行、按 `revenue` 降序；**每行净额与订单数都与参考结果逐行一致** |
| `t3` 反连接做数据质量检查 | `c4` | `orphan_orders` | 结果为 0 行，且列结构与 `orders` 完全一致（说明用的是 `anti`，而不是「左连接后过滤空值」） |

`c1` 已经读好两张表并打印 shape 与 head；从 `c2` 开始每格只留了 `# TODO` 和占位赋值，先跑出「未完成」的样子，再逐步补全。

## 常见坑

**错误 1：join 后列名冲突**
```python
# 两张表有同名列（除 join key 外）时，Polars 会自动加后缀 _right
print([c for c in orders_customers.columns if c.endswith("_right")])
```

**错误 2：忘记指定 how，默认 inner 丢了行**
```python
orders.join(users, on="user_id")              # 默认 inner，可能静默丢行
orders.join(users, on="user_id", how="left")  # 分析中推荐显式 left
```

**错误 3：on 和 left_on/right_on 用混**
```python
df.join(dim, on="product_id", how="left")                   # 同名列
df.join(dim, left_on="prod_id", right_on="id", how="left")  # 不同名列
```

**错误 4：连接后行数变多，却以为数据变全了**
```python
# 右表键重复时，左表一行会被放大成多行
print(customers["customer_id"].is_unique())   # 先确认右表键唯一
print(orders.height, orders.join(customers, on="customer_id", how="left").height)
```

**错误 5：用 anti 前没确认键的类型一致**
```python
# 两个 customer_id 都是字符串；若把客户表读成整数，
# anti 会把 5000 行全部报成孤儿——这种「全错」通常不是数据脏，而是键没对上
print(orders.schema["customer_id"], customers.schema["customer_id"])
```
## 自检清单

- [ ] 连接后行数仍是 5000（不是 800，也不是 5000 的倍数）
- [ ] 输出里没有 `segment_right`、`region_right` 之类的多余列，也没有把客户区域当成下单区域
- [ ] `segment_stats` 的 `revenue` 合计是 5,034,517.88（直接用 `amount` 求和会得到 5,287,843.86，那是没扣退款）
- [ ] `orphan_orders` 是空表，但列结构和 `orders` 一致
- [ ] 能说清 `left` / `inner` / `semi` / `anti` 各自适合什么场景

## 下一步建议

完成本课后，建议继续：
- **DuckDB SQL 分型基础**：学习用 SQL 的 JOIN 写法做同样的事情
- 对比 Polars join 和 SQL JOIN 的写法差异
