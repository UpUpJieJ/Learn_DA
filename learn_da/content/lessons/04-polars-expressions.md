---
id: 4
slug: polars-expressions
title: Polars 表达式与列计算
category: polars
difficulty: beginner
estimated_minutes: 25
order: 4
tags: [polars, expression, with_columns, 列计算]
prev_lesson:
  slug: polars-groupby
  title: Polars 分组聚合
next_lesson:
  slug: polars-cleaning
  title: Polars 数据清洗
practice_objective: >-
  掌握 Polars 表达式的核心写法，能用 with_columns 完成列计算、
  用 pl.when().then().otherwise() 完成条件分层。
completion_criteria:
  - 用 with_columns + 算术表达式创建派生列
  - 用 pl.when().then().otherwise() 做条件分层
  - 用 alias() 给新列命名
  - 用 pl.lit() 插入常量值
# Phase 3: 建议系统元数据
track: polars_basics
prerequisites: ['polars-basics', 'polars-groupby']
recommended_next: ['polars-cleaning']
skill_tags: ['expressions', 'with_columns', 'conditional_logic', 'pl_when']
is_review_friendly: true
is_branch_point: false
exercise:
  id: polars-expressions-revenue-band-v1
  title: 计算收入并给价格分层
  language: python
  starter_code: |
    import polars as pl

    products = pl.DataFrame({
        "product": ["键盘", "鼠标", "显示器", "耳机", "音箱"],
        "price": [199, 89, 1299, 299, 450],
        "cost": [120, 45, 800, 150, 280],
        "quantity": [5, 12, 2, 7, 3],
    })

    # TODO: 用 with_columns 添加 revenue（price × quantity），
    # 并用 pl.when().then().otherwise() 添加 price_band（price ≥ 500 为"高价"，其余为"平价"）
    result = products
    print(result)
  objective: |
    用 with_columns 一次添加两个派生列：revenue 为 price 乘 quantity，
    price_band 用条件表达式按 price 是否 ≥ 500 分层。
  hints:
    - (pl.col('price') * pl.col('quantity')).alias('revenue')
    - pl.when(pl.col('price') >= 500).then(pl.lit('高价')).otherwise(pl.lit('平价')).alias('price_band')
    - 多个派生列可以写在同一个 with_columns 中
  validator:
    type: dataframe_rows
    expected:
      columns: [product, revenue, price_band]
      row_count: 5
# 改版 M1：多 cell 工作区（重放式，严格顺序）
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
        # TODO: 在 orders 上新增两列：gross = unit_price * quantity，
        # net_amount = unit_price * quantity * discount（保留两位小数）
        with_amounts = orders
        print(with_amounts.head(3))
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 在 with_amounts 上新增 amount_tier 列：
        # amount >= 500 为高客单，>= 200 为中客单，其余为低客单
        tiered_orders = with_amounts
        print(tiered_orders.head(5))
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 在 tiered_orders 上新增两列：
        # source 整列都是 ecommerce（用 pl.lit），amount_k = amount / 1000 保留两位小数
        tagged_orders = tiered_orders
        print(tagged_orders.head(3))
  tasks:
    - id: t1
      title: 派生原价与折后金额
      cell: c2
      objective: |
        用 with_columns 给 orders 新增 gross（unit_price * quantity）与
        net_amount（unit_price * quantity * discount，保留两位小数）两列，
        结果命名为 with_amounts，行数仍是 5000。
      assertions:
        - id: t1-schema
          type: schema
          title: with_amounts 新增 gross 与 net_amount
          var: with_amounts
          columns: [order_id, unit_price, quantity, discount, gross, net_amount]
        - id: t1-rows
          type: expr_true
          title: 行数不变（5000）
          expr: "with_amounts.height == 5000"
        - id: t1-gross
          type: expr_true
          title: gross 合计等于单价乘数量的总和
          expr: "abs(with_amounts['gross'].sum() - 5717859.02) < 1.0"
        - id: t1-net
          type: expr_true
          title: net_amount 合计正确且与实付列 amount 只差分位舍入
          expr: "abs(with_amounts['net_amount'].sum() - 5287843.90) < 1.0 and (with_amounts['net_amount'] - with_amounts['amount']).abs().max() < 0.02"
    - id: t2
      title: 按客单价做条件分层
      cell: c3
      objective: |
        在 with_amounts 上用 pl.when().then().otherwise() 新增 amount_tier 列：
        amount >= 500 为高客单，>= 200 为中客单，其余为低客单。结果命名为 tiered_orders。
      assertions:
        - id: t2-schema
          type: schema
          title: tiered_orders 含 amount 与 amount_tier
          var: tiered_orders
          columns: [amount, amount_tier]
        - id: t2-counts
          type: expr_true
          title: 高客单 1886 单、低客单 1936 单
          expr: "tiered_orders.filter(pl.col('amount_tier') == '高客单').height == 1886 and tiered_orders.filter(pl.col('amount_tier') == '低客单').height == 1936"
        - id: t2-low-bound
          type: expr_true
          title: 低客单的最大金额小于 200
          expr: "tiered_orders.filter(pl.col('amount_tier') == '低客单')['amount'].max() < 200"
        - id: t2-high-bound
          type: expr_true
          title: 高客单的最小金额不小于 500
          expr: "tiered_orders.filter(pl.col('amount_tier') == '高客单')['amount'].min() >= 500"
    - id: t3
      title: 用 pl.lit 打标并换算金额
      cell: c4
      objective: |
        在 tiered_orders 上新增两列：source 整列都是 ecommerce（用 pl.lit），
        amount_k = amount / 1000 并保留两位小数。结果命名为 tagged_orders。
      assertions:
        - id: t3-schema
          type: schema
          title: tagged_orders 含 source 与 amount_k
          var: tagged_orders
          columns: [source, amount_k]
        - id: t3-source
          type: expr_true
          title: source 只有一个取值 ecommerce
          expr: "tagged_orders['source'].unique().to_list() == ['ecommerce']"
        - id: t3-sum
          type: expr_true
          title: amount_k 合计约为 5288.34（千元，两位小数）
          expr: "abs(tagged_orders['amount_k'].sum() - 5288.34) < 0.05"
        - id: t3-rows
          type: expr_true
          title: 打标不增加也不减少行（5000）
          expr: "tagged_orders.height == 5000"
---
# Polars 表达式与列计算

## 这节课解决什么问题

上一课用筛选和排序回答了"哪些订单"，但运营真正关心的是**算出来的指标**：原价金额、折后金额、
客单价分层。这些指标原始表里没有，必须靠表达式现场算出来。

这一课解决三件事：**用算术表达式一次派生多列**（原价 / 折后价）、**用条件表达式把连续金额切成
高 / 中 / 低三档**、**用 `pl.lit` 把常量写进表做数据来源标记**。这三招几乎出现在每份业务报表里，
学会之后你写的 `with_columns` 就是一个小型指标计算器。

## 你将用到的数据

工作区读的是 `data/ecommerce/orders.csv`（**5000 行 × 11 列**，一个订单一行，2025 全年）。

| 列名 | 类型 | 含义 |
|------|------|------|
| `order_id` | str | 订单号，全表唯一 |
| `quantity` | int | 购买件数，1-5 |
| `unit_price` | float | 下单时单价快照 |
| `discount` | float | 折扣系数，0.8 / 0.85 / 0.9 / 1.0 |
| `amount` | float | 实付金额 = `round(unit_price * quantity * discount, 2)` |
| `channel` | str | 下单渠道：`app` / `web` / `mini_program` / `offline` |

已知的坑：

- `amount` 已经是**折后**金额，`unit_price * quantity` 是**原价**，两个指标一起算才有对比价值。
- `discount` 是系数不是百分比（`0.9` 是九折，`1.0` 是没打折）；客单价分层看单笔实付 `amount`，不是单价 `unit_price`。
- 自己重算的折后金额和 `amount` 列会在部分行差 1 分钱（浮点舍入路径不同），比对时要留容差。

## Pandas → Polars 对照

| Pandas | Polars | 说明 |
|--------|--------|------|
| `df['a'] * df['b']` | `pl.col('a') * pl.col('b')` | Polars 用 `pl.col()` 引用列 |
| `df.assign(y = df.x * 2)` | `df.with_columns((pl.col('x') * 2).alias('y'))` | Polars 用表达式 + alias |
| `np.where(cond, a, b)` | `pl.when(cond).then(a).otherwise(b)` | Polars 内置条件表达式 |

## 核心概念与派生指标

表达式不马上取值，而是描述"要怎样计算"：`pl.col` 引用列、`pl.lit` 造字面量、`alias` 命名结果、
`pl.when().then().otherwise()` 做分支。多列计算一次提交给 Polars，便于优化和并行。

```python
import polars as pl

df = pl.DataFrame({
    "product": ["键盘", "鼠标", "显示器", "耳机"], "price": [199, 89, 1299, 299],
    "quantity": [5, 12, 2, 7],
})
result = df.with_columns(
    (pl.col("price") * pl.col("quantity")).alias("revenue"),
    (pl.col("price") >= 300).alias("is_high_price"),
)
print(result)
```

`with_columns` 返回新 DataFrame，原 `df` 不变。同一批表达式之间**不能互相引用**：后一列要用前一列
的结果，必须再调一次 `with_columns`。

## 条件分层

`pl.when().then().otherwise()` 就是 Polars 的 if-elif-else：

```python
result = df.with_columns(
    pl.when(pl.col("price") >= 500).then(pl.lit("高价"))
    .when(pl.col("price") >= 200).then(pl.lit("中价"))
    .otherwise(pl.lit("低价")).alias("price_band")
)
```

条件从上往下匹配，第一个满足的就生效，所以**阈值必须从大到小写**，顺序反了后面的分支永远走不到。
`then` / `otherwise` 里的常量要用 `pl.lit()` 包起来（变成"长度 1、自动广播"的列），否则会报错或产出怪列名。

## 练习

基于下面的小数据：用 `with_columns` 添加 `revenue`（price × quantity）和 `profit`
（(price - cost) × quantity），再用 `pl.when()` 按 `profit` 分高 / 中 / 低利润，最后只保留四列：

```python:example
import polars as pl
products = pl.DataFrame({
    "product": ["键盘", "鼠标", "显示器", "耳机", "音箱"],
    "price": [199, 89, 1299, 299, 450],
    "cost": [120, 45, 800, 150, 280],
    "quantity": [5, 12, 2, 7, 3],
})

result = products.with_columns(
    (pl.col("price") * pl.col("quantity")).alias("revenue"),
    ((pl.col("price") - pl.col("cost")) * pl.col("quantity")).alias("profit"),
).with_columns(
    pl.when(pl.col("profit") >= 1000).then(pl.lit("高利润"))
    .when(pl.col("profit") >= 300).then(pl.lit("中利润"))
    .otherwise(pl.lit("低利润")).alias("profit_level")
).select(["product", "revenue", "profit", "profit_level"])
print(result)
```

这是**通用小例子**。工作区里的三个任务换成 5000 行真实订单，指标换成原价金额、折后金额与客单价分层——
动作结构一样，但变量名与阈值必须按任务说明来。

## 任务清单

右边工作区按顺序做：**当前任务的断言全部通过才解锁下一个**。三个任务共享同一个命名空间，
变量名必须与下面完全一致。

- **t1 派生原价与折后金额**（c2）：产出 `with_amounts`，新增 `gross = unit_price * quantity` 与
  `net_amount = unit_price * quantity * discount`（保留两位小数），行数 5000；验收比对 `gross` 合计并要求两列只差浮点舍入。
- **t2 按客单价做条件分层**（c3）：产出 `tiered_orders`，用 `pl.when().then().otherwise()` 新增
  `amount_tier`（`amount >= 500` 高客单、`>= 200` 中客单、其余低客单）；验收比对三档数量与边界。
- **t3 用 pl.lit 打标并换算金额**（c4）：产出 `tagged_orders`，`source` 整列都是 `ecommerce`（用 `pl.lit`），
  `amount_k = amount / 1000` 保留两位小数；验收检查 `source` 唯一取值与 `amount_k` 合计。

## 常见坑

**错误 1：忘记 alias，列名变成表达式字符串**
```python
df.with_columns(pl.col("price") * 1.1)                          # 列名不可读
df.with_columns((pl.col("price") * 1.1).alias("new_price"))     # 始终 alias
```

**错误 2：when 条件顺序错误，或条件里写 Python 原生比较**
```python
# 错误：>= 100 会匹配所有 >= 1000 的行，后面的条件永远不触发
pl.when(pl.col("x") >= 100).then(...).when(pl.col("x") >= 1000).then(...)
pl.when('price' > 100).then(...)          # 错：这是字符串比较，不是列比较
# 正确：从最严格的条件开始，条件是 pl.col() 表达式
pl.when(pl.col("x") >= 1000).then(...).when(pl.col("x") > 100).then(...)
pl.when(pl.col("price") > 100).then(...)
```

**错误 3（本数据集特有）：分层用错字段，或把 discount 当折扣率相减**
```python
pl.when(pl.col('unit_price') >= 500).then(pl.lit('高客单'))   # 错：这是价位段，不是客单价段
pl.when(pl.col('amount') >= 500).then(pl.lit('高客单'))       # 正确
(pl.col('unit_price') * pl.col('quantity') * (1 - pl.col('discount')))   # 错：系数不能当折扣率减
(pl.col('unit_price') * pl.col('quantity') * pl.col('discount'))        # 正确
```

**错误 4：一次 `with_columns` 里让后一列引用前一列**
```python
# 错误：同一批表达式并行计算，net 拿不到刚定义的 gross
df.with_columns(gross=..., (pl.col('gross') * pl.col('discount')).alias('net'))
# 正确：拆成两次 with_columns
```

## 自检清单

- [ ] `gross` 用 `unit_price * quantity`、`net_amount` 再乘 `discount`，两者没混；同一次 `with_columns` 里没让后列引用前列
- [ ] `when` 阈值从大到小写，每个分支都用 `pl.lit` 包了常量并 `alias` 了结果
- [ ] 三档 `amount_tier` 的行数加起来正好 5000，`source` 是 `pl.lit('ecommerce')` 生成的

## 下一步建议

- **Polars 数据清洗**：缺失值处理、类型转换、文本规范化——脏数据在表达式中会遇到的新问题
- 在 Playground 中对你的数据做条件分层（如按金额分为大 / 中 / 小单），练熟 `when().then()`
