---
id: 1
slug: polars-basics
title: Polars 基础入门
category: polars
difficulty: beginner
estimated_minutes: 20
order: 1
tags: [polars, dataframe, 入门, select, filter, with_columns]
next_lesson:
  slug: duckdb-analytics
  title: DuckDB 查询分析
practice_objective: >-
  掌握 Polars 的 DataFrame 创建、列选择、行筛选和列派生，
  能把 Pandas 中最常用的操作映射到 Polars 对应写法。
completion_criteria:
  - 使用 pl.DataFrame 创建包含至少 3 列的 DataFrame
  - 用 select 选取指定列
  - 用 filter 按条件筛选行
  - 用 with_columns 添加一个派生列
# Phase 3: 建议系统元数据
track: polars_basics
prerequisites: []
recommended_next: [duckdb-analytics, polars-groupby]
skill_tags: [dataframe_basics, column_selection, row_filtering, column_derivation]
is_review_friendly: true
is_branch_point: false
workspace:
  datasets:
    - ecommerce/orders.csv
  cells:
    - id: c1
      kind: starter
      code: |
        import polars as pl

        orders = pl.read_csv("data/ecommerce/orders.csv")
        print(orders.shape)
        print(orders.head(3))
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: 从 orders 里筛出渠道为 app 的订单，只保留 order_id / region / amount 三列
        app_orders = orders
        print(app_orders.head(5))
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 在 orders 上新增 gross 列 = unit_price * quantity，其余原始列全部保留
        with_gross = orders
        print(with_gross.head(3))
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 取 amount 金额最高的 10 单，只保留 order_id / region / channel / amount 四列
        top_orders = orders
        print(top_orders.head(5))
  tasks:
    - id: t1
      title: 筛选 app 渠道订单并挑列
      cell: c2
      objective: |
        从 orders 筛出 channel 为 app 的订单，再用 select 只保留 order_id、region、amount 三列，
        结果命名为 app_orders。
      assertions:
        - id: t1-schema
          type: schema
          title: app_orders 含 order_id / region / amount 三列
          var: app_orders
          columns: [order_id, region, amount]
        - id: t1-rows
          type: expr_true
          title: 行数等于 app 渠道订单数（1272）
          expr: "app_orders.height == 1272"
        - id: t1-sum
          type: expr_true
          title: 这批订单的 amount 合计与数据集一致
          expr: "abs(app_orders['amount'].sum() - 1362720.69) < 0.5"
    - id: t2
      title: 派生订单原价金额 gross
      cell: c3
      objective: |
        用 with_columns 给 orders 新增 gross 列 = unit_price * quantity，
        原始 11 列全部保留，结果命名为 with_gross。
      assertions:
        - id: t2-schema
          type: schema
          title: with_gross 保留原始列并新增 gross
          var: with_gross
          columns: [order_id, channel, unit_price, quantity, amount, gross]
        - id: t2-rows
          type: expr_true
          title: with_columns 不改变行数（5000）
          expr: "with_gross.height == 5000"
        - id: t2-sum
          type: expr_true
          title: gross 合计等于单价乘数量的总和
          expr: "abs(with_gross['gross'].sum() - 5717859.02) < 1.0"
        - id: t2-max
          type: expr_true
          title: gross 最大值符合数据集（19236.8）
          expr: "abs(with_gross['gross'].max() - 19236.8) < 0.01"
    - id: t3
      title: 取金额最高的 10 单
      cell: c4
      objective: |
        用 sort 按 amount 降序排列再取前 10 行，并只保留 order_id、region、channel、amount 四列，
        结果命名为 top_orders。
      assertions:
        - id: t3-schema
          type: schema
          title: top_orders 只含四个指定列
          var: top_orders
          columns: [order_id, region, channel, amount]
          exact: true
        - id: t3-sorted
          type: expr_true
          title: amount 从大到小排列
          expr: "top_orders['amount'].to_list() == sorted(top_orders['amount'].to_list(), reverse=True)"
        - id: t3-exact
          type: frame_equal
          title: 十行订单的行与列与参考结果一致（金额并列时顺序不限）
          var: top_orders
          ref: 01-t3-top-orders.parquet
          order_matters: false
          rtol: 1e-6
---

# Polars 基础入门

## 这节课解决什么问题

运营同学把全年 5000 条订单明细交给你，问三件事：**app 渠道卖了多少？每笔订单的原价金额（不扣折扣）是多少？
金额最高的 10 单是谁？**

三个问题覆盖了分析里最常用的一组动作：**筛行、挑列、加列、排序取前 N**。它们也是后面分组聚合、
窗口函数、连接的地基。这一课的重点不是背 API，而是建立「用 `pl.col()` 描述列、再交给 DataFrame 执行」
的表达式直觉；学完你能读懂任意一段链式调用的执行顺序。

## 你将用到的数据

工作区读的是 `data/ecommerce/orders.csv`（**5000 行 × 11 列**，一个订单一行，2025 全年）。

| 列名 | 类型 | 含义 |
|------|------|------|
| `order_id` | str | 订单号，`O000001` 形式，全表唯一 |
| `region` | str | 客户所属大区：华东 / 华北 / 华南 / 西南 |
| `channel` | str | 下单渠道：`app` / `web` / `mini_program` / `offline`（**全小写**） |
| `quantity` | int | 购买件数，1-5 |
| `unit_price` | float | 下单时的商品单价快照 |
| `discount` | float | 折扣系数，0.8 / 0.85 / 0.9 / 1.0 |
| `amount` | float | 实付金额 = `round(unit_price * quantity * discount, 2)` |
| `order_date` | str | 下单日期 `2025-01-01` ~ `2025-12-31`（读进来是字符串） |

已知的坑：

- `amount` 是**打过折**的实付金额，`unit_price * quantity` 才是原价金额，两者不是一回事。
- `discount` 是 0.8-1.0 的**系数**，不是百分比，不要写成 `unit_price * quantity * (1 - discount)`。
- `order_date` 目前是字符串，本课不需要转换。

## 从 Pandas 迁移的直觉对照

| Pandas | Polars | 说明 |
|--------|--------|------|
| `pd.DataFrame({...})` | `pl.DataFrame({...})` | 创建方式几乎一样 |
| `df[['col1', 'col2']]` | `df.select(['col1', 'col2'])` | Polars 用方法，不用索引 |
| `df[df['x'] > 10]` | `df.filter(pl.col('x') > 10)` | Polars 用 `pl.col()` 引用列 |
| `df.assign(y = df.x * 2)` | `df.with_columns((pl.col('x') * 2).alias('y'))` | Polars 用表达式 |
| `df.sort_values('x', ascending=False).head(10)` | `df.sort('x', descending=True).head(10)` | 排序 + 取前 N |

Polars 用 Rust 实现、列式存储、支持并行与惰性求值，所以在同样硬件上通常比 Pandas 快数倍。

## 创建 DataFrame 与 select / filter

```python
import polars as pl

df = pl.DataFrame({
    'city': ['beijing', 'shanghai', 'shenzhen'],
    'sales': [120, 98, 135],
})

df.select(['city', 'sales'])            # 选列
df.filter(pl.col('sales') > 100)        # 选行：保留 beijing 与 shenzhen
```

Polars 中引用列一律用 `pl.col('列名')`，而不是 `df['列名']`，这是和 Pandas 最大的写法差异。
`filter` 返回的仍是 DataFrame，可以继续链式调用，**执行顺序就是书写顺序**：

> 先用行过滤把数据缩小，再用列选择把表变窄，最后才做派生和排序。

一旦顺序反了（先 `select` 丢掉 `channel`，再 `filter(pl.col('channel') == 'app')`），就会直接报错。

## with_columns

```python
result = df.with_columns((pl.col('sales') * 1.1).alias('sales_next_year'))
print(result)
```

`with_columns` 不会修改原 DataFrame，而是返回新的。两个细节：

1. 不写 `alias()` 时新列名会变成表达式字符串，可读性极差。
2. 同一次 `with_columns` 里的多个表达式**不能互相引用**（`gross` 和 `gross * 0.9` 要分两次调用）。

## 排序与取前 N 行

```python
top_cities = df.sort('sales', descending=True).head(2)   # 销售额最高的 2 个城市
print(top_cities)
```

`sort` 默认升序，降序要写 `descending=True`；`head(n)` 取前 n 行。排序是**稳定**的：金额相同的行保持
原始顺序，所以并列时的"第 10 名"取到哪一行取决于原始顺序，报表里要说明口径。

## 练习

基于下面的小数据，先用 `select` 取 `product` 和 `price`，再用 `filter` 筛 `price > 100`，
然后用 `with_columns` 加 `total = price * quantity`，最后筛 `total > 500` 并只保留 `product` 和 `total`：

```python:example
import polars as pl

orders = pl.DataFrame({
    'product': ['键盘', '鼠标', '显示器', '耳机'],
    'price': [200, 80, 1500, 300],
    'quantity': [3, 5, 1, 2],
})

with_total = orders.with_columns(
    (pl.col('price') * pl.col('quantity')).alias('total')
)
result = with_total.filter(pl.col('total') > 500).select(['product', 'total'])
print(result)
```

这是**通用小例子**。工作区里的三个任务换成真实订单表，规模大 1000 倍，动作完全一样——
差别在于你必须自己决定筛哪个渠道、留哪些列、排哪个字段。

## 任务清单

右边工作区按顺序做：**当前任务的断言全部通过才解锁下一个**。三个任务共享同一个命名空间，
变量名必须与下面完全一致，断言是按变量名取值的。

- **t1 筛选 app 渠道订单并挑列**（c2）：产出 `app_orders`。只留 `app` 渠道，只保留
  `order_id`、`region`、`amount` 三列；行数与金额合计都要对得上数据集。注意渠道值是小写。
- **t2 派生订单原价金额 gross**（c3）：产出 `with_gross`。新增 `gross = unit_price * quantity`，
  **原始 11 列一列都不能少**，行数仍为 5000。别把折后的 `amount` 当原价。
- **t3 取金额最高的 10 单**（c4）：产出 `top_orders`。按 `amount` 降序取前 10 行，只保留
  `order_id`、`region`、`channel`、`amount` 四列。注意先排序再取前 N，否则拿到的是前 10 行里的最大值。

## 常见坑

**错误 1：用 Pandas 语法写 Polars**
```python
df[df['sales'] > 100]              # 报错
df.filter(pl.col('sales') > 100)   # 正确
```

**错误 2：忘记 `pl.col()`**
```python
df.filter('sales' > 100)           # 字符串比较，不是列操作
df.filter(pl.col('sales') > 100)   # 正确
```

**错误 3：以为 `with_columns` 会修改原对象**
```python
new_df = df.with_columns(...)      # 结果在 new_df 里，df 不变
```

**错误 4（本数据集特有）：把 `amount` 当成原价金额**
```python
orders.with_columns(pl.col('amount').alias('gross'))   # 错：amount 已乘过 discount
orders.with_columns((pl.col('unit_price') * pl.col('quantity')).alias('gross'))
```

**错误 5（本数据集特有）：先 `select` 再 `filter`**
```python
orders.select(['order_id', 'amount']).filter(pl.col('channel') == 'app')   # 错：channel 已被裁掉
orders.filter(pl.col('channel') == 'app').select(['order_id', 'amount'])   # 正确
```

## 自检清单

- [ ] 我能说清 `filter` / `select` / `with_columns` 各自改变 DataFrame 的哪个维度（行 / 列）
- [ ] `app_orders` 只有三列，且每一行的金额都与参考结果一致
- [ ] `with_gross` 保留原始 11 列，`gross` 用 `unit_price * quantity` 而不是 `amount`
- [ ] `top_orders` 先排序再取前 10 行，金额降序，且十行与参考结果一致

## 下一步建议

- **DuckDB 查询分析**：学习用 SQL 查询同一份数据，对比 Polars 与 SQL 的表达差异
- 回到 Playground，用你自己的数据创建 DataFrame 并做筛选