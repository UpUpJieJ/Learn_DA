---
id: 10
slug: polars-lazy-pipeline
title: Polars 惰性流水线
category: polars
difficulty: intermediate
estimated_minutes: 35
order: 10
tags: [polars, lazy, pipeline, query optimization, performance]
prev_lesson:
  slug: duckdb-window-functions
  title: DuckDB 窗口函数
next_lesson:
  slug: polars-duckdb-workflow
  title: Polars 与 DuckDB 组合工作流
practice_objective: >-
  理解 Polars 的 eager 和 lazy 两种执行模式，
  能用 lazy() + collect() 构建可优化的分析流水线。
completion_criteria:
  - 用 .lazy() 将 DataFrame 转为惰性模式
  - 在惰性模式下链式调用 filter、with_columns、group_by
  - 用 .collect() 触发实际计算
  - 理解惰性模式为什么更适合复杂分析
# Phase 3: 建议系统元数据
track: polars_advanced
prerequisites: [polars-basics, polars-groupby, polars-expressions]
recommended_next: [polars-duckdb-workflow]
skill_tags: [lazy_evaluation, query_optimization, pipeline, performance]
is_review_friendly: false
is_branch_point: true
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
        # TODO: 用 .lazy() 进入惰性模式，过滤掉已退款订单和 amount < 100 的订单，
        # 再派生优惠前金额 list_amount（amount / discount，保留两位），最后 collect()
        filtered = orders
        print(filtered.shape)
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 基于 filtered 继续惰性链：group_by region + agg 出 revenue 与 orders，
        # 按 revenue 降序，链尾 collect() 得到 region_stats
        region_stats = filtered
        print(region_stats)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 把「过滤已退款订单 + 按 region 汇总金额 + 按金额降序」写成 pipeline（仍是 LazyFrame），
        # 用 plan_text 保存 explain() 的结果，最后 collect() 得到 lazy_result
        pipeline = orders.lazy()
        plan_text = ""
        lazy_result = orders
        print(plan_text)
  tasks:
    - id: t1
      title: 惰性过滤 + 派生列
      cell: c2
      objective: |
        用 orders.lazy() 进入惰性模式，filter 掉 refunded 为 True 以及 amount < 100 的订单，
        再用 with_columns 派生 list_amount = amount / discount（保留两位小数），
        最后 collect() 得到名为 filtered 的 DataFrame。
      assertions:
        - id: t1-schema
          type: schema
          title: 结果包含 order_id / amount / list_amount 三列
          var: filtered
          columns: [order_id, amount, list_amount]
        - id: t1-rows
          type: expr_true
          title: 过滤后剩 3722 行（已退款与小额订单一笔不留）
          expr: "filtered.height == 3722"
        - id: t1-min
          type: expr_true
          title: 最小金额仍在 100 元以上
          expr: "filtered['amount'].min() >= 100"
        - id: t1-list
          type: expr_true
          title: list_amount 合计 5,373,637.19 元（优惠前金额算对了）
          expr: "abs(filtered['list_amount'].sum() - 5373637.19) < 0.05"
    - id: t2
      title: 惰性分组聚合
      cell: c3
      objective: |
        基于 filtered 继续惰性链：group_by('region') + agg 计算 revenue（amount 求和）
        与 orders（订单数），按 revenue 降序，链尾 collect() 得到 region_stats。
      assertions:
        - id: t2-schema
          type: schema
          title: 结果包含 region / revenue / orders 三列
          var: region_stats
          columns: [region, revenue, orders]
        - id: t2-exact
          type: frame_equal
          title: 四个区域的金额与订单数与参考结果逐行一致
          var: region_stats
          ref: 10-t2-region-stats.parquet
          order_matters: true
          rtol: 1e-6
    - id: t3
      title: 用 explain() 观察执行计划
      cell: c4
      objective: |
        把「filter 未退款 + group_by region 求 revenue + 按 revenue 降序」写成 pipeline（LazyFrame），
        plan_text 保存 pipeline.explain() 的输出（断言会用 .upper() 归一大小写），
        最后 collect() 得到 lazy_result。
      assertions:
        - id: t3-filter
          type: expr_true
          title: 执行计划里出现 FILTER 算子
          expr: "'FILTER' in plan_text.upper()"
        - id: t3-aggregate
          type: expr_true
          title: 执行计划里出现 AGGREGATE 算子
          expr: "'AGGREGATE' in plan_text.upper()"
        - id: t3-sort
          type: expr_true
          title: 执行计划里出现 SORT 算子
          expr: "'SORT' in plan_text.upper()"
        - id: t3-collect
          type: expr_true
          title: collect() 后得到 4 行、region 与 revenue 两列的 DataFrame
          expr: "lazy_result.height == 4 and lazy_result.columns == ['region', 'revenue']"
---

# Polars 惰性流水线

## 这节课解决什么问题

`orders.csv` 有 5000 笔订单。分析师常写的一串操作是：先剔掉已退款的订单（约 4%）、再剔掉金额太小的订单、派生出优惠前金额、最后按区域汇总。Eager 模式下每一步都会立刻产出一份完整中间结果，5000 行还好，到了几百万行就是内存与时间的双重浪费。

惰性模式把这条链改成「先描述、后执行」：`.lazy()` 之后所有操作只是在拼计划，直到 `.collect()` 才一次算完。Polars 还会顺手做优化——把过滤条件下推、只读需要的列。本课你要交付三段流水线：`filtered`（过滤 + 派生列）、`region_stats`（分组聚合 + 排序）、以及一份能读懂的执行计划 `plan_text`。

## 你将用到的数据

`data/ecommerce/orders.csv`（5000 行，11 列，本课只用到下面几列）

| 字段 | 类型 | 含义 |
|---|---|---|
| `order_id` | str | `O000001` 形式的订单号，唯一 |
| `region` | str | 下单区域：华东 / 华北 / 华南 / 西南 |
| `amount` | float | 订单实付金额（已含数量与折扣） |
| `discount` | float | 0.8 / 0.85 / 0.9 / 1.0 |
| `refunded` | bool | 是否已退款，约 4% |

已知坑：

- `refunded` 是布尔列，过滤未退款用 `~pl.col("refunded")`；写 `== "False"` 会一行都留不下。
- `collect()` 之前拿到的是 `LazyFrame`，没有 `.height` / `.shape`，直接打印只会看到计划而不是数据。
- `explain()` 的文本里算子名是英文大写（`FILTER` / `AGGREGATE` / `SORT`），但不同 Polars 版本的大小写与措辞会有差异，比较前统一 `.upper()` 更稳。
- 过滤后剩 3722 行，营收合计 4,968,434.34 元——这两个数是本课的校验基准。

## Eager vs Lazy

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| Eager（默认） | 每一步立即执行并返回结果 | 快速查看数据、简单操作 |
| Lazy | 先描述计算计划，`collect()` 时才执行 | 多步分析、大数据、需要优化 |

一句话：Eager 是「说一步做一步」，Lazy 是「把计划说完再一起做」。惰性模式的好处是**查询优化**（合并过滤、只读需要的列）、**内存友好**（不生成一堆中间 DataFrame）和**链式写法**（一条流水线表达整个分析）。

写法就一句：`orders.lazy() → .filter(...) → .with_columns(...) → .group_by(...) → .collect()`。
## 构建惰性分析流程

```python:example
import polars as pl

orders = pl.DataFrame({
    "order_id": [1, 2, 3, 4, 5],
    "region": ["华东", "华东", "华南", "华南", "华北"],
    "category": ["办公", "数码", "办公", "配件", "办公"],
    "amount": [120, 899, 240, 59, 180],
})

query = (
    orders.lazy()                                 # 进入惰性模式：只拼计划
    .filter(pl.col("amount") >= 100)
    .with_columns(
        pl.when(pl.col("amount") >= 500)
        .then(pl.lit("大额"))
        .otherwise(pl.lit("普通"))
        .alias("amount_band")
    )
    .group_by(["region", "amount_band"])
    .agg(pl.len().alias("order_count"), pl.col("amount").sum().alias("total_amount"))
    .sort("total_amount", descending=True)
)

print(type(query))       # LazyFrame：还不算
print(query.collect())   # collect() 才真正执行
```
## 什么时候使用 lazy

| 场景 | 建议 |
|------|------|
| 查看前几行、简单筛选 | 用 Eager（默认） |
| 3 步以上的分析流水线 | 用 Lazy |
| 读取大文件 + 多步处理 | 用 Lazy（优化后更省内存） |
| 需要链式写法表达分析逻辑 | 用 Lazy |

## 读懂 explain() 输出

`pipeline.explain()` 返回的是**优化后**的逻辑计划，从上往下读就是执行顺序。一个典型输出：

```text
SORT BY [descending: [true]] [col("revenue")]
  AGGREGATE[maintain_order: false]
    [col("amount").sum().alias("revenue")] BY [col("region")]
    FROM
    simple π 2/11 ["amount", "region"]
      FILTER [(col("refunded")) == (false)]
      FROM
        DF ["order_id", "customer_id", ...]; PROJECT["amount", "region", "refunded"]
```

三件事值得注意：

1. **算子自上而下**：`SORT` 在最上，说明排序是最后一步；`FILTER` 沉到最底下，说明过滤被下推到了读数据的旁边。
2. **`simple π 2/11`**：投影下推——11 列里只有 2 列被真正读上来（`π` 是关系代数里的投影符号）。
3. **`explain()` 不执行查询**：它只打印计划；要看结果仍然得 `.collect()`。

## 动手练

拿上文那格示例里的 6 行玩具数据，亲手改三处再跑一遍：

- 把 `pipeline.explain()` 打印的计划和 `pipeline.collect()` 的结果对照一遍，指出 `FILTER` 落在第几层；
- 删掉 `.sort(...)`，看计划最上面的 `SORT BY` 是否消失；
- 把过滤条件从 `>= 100` 改成 `> 500`，解释为什么 `AGGREGATE` 那一层的分组结果少了一行。
## 任务清单

右边工作区按 `c1 → c2 → c3 → c4` 顺序执行，**当前任务通过后才解锁下一个**。`c1` 已经读入 `orders` 并打印 shape 与 head。

| 任务 | 单元格 | 要交付的变量 | 验收标准 |
|---|---|---|---|
| `t1` 惰性过滤 + 派生列 | `c2` | `filtered` | 3722 行、最小金额 ≥ 100、`list_amount` 合计 5,373,637.19 元 |
| `t2` 惰性分组聚合 | `c3` | `region_stats` | 四行、按 `revenue` 降序；**每行营收与订单数都与参考结果逐行一致** |
| `t3` 观察执行计划 | `c4` | `plan_text` / `lazy_result` | 计划里出现 FILTER / AGGREGATE / SORT，`collect()` 后是 4 行 2 列 |

`t3` 的 `plan_text` 要保存 `explain()` 返回的**整段字符串**，不要自己截断或改写——断言会先 `.upper()` 再找关键字，所以大小写不用管。

## 常见坑

**错误 1：在 LazyFrame 上直接 print**
```python
query = orders.lazy().filter(pl.col("amount") > 100)
print(query)            # 打印的是 LazyFrame 对象，不是数据
print(query.collect())  # 这才执行
```

**错误 2：忘记 collect() 就写出文件**
```python
orders.lazy().filter(...).write_csv("out.csv")            # 行为异常
orders.lazy().filter(...).collect().write_csv("out.csv")  # 正确
```

**错误 3：在 lazy 链里混用 eager 操作**
```python
orders.lazy().filter(...).head(10)            # head 在 lazy 下语义可选，容易误用
orders.lazy().filter(...).collect().head(10)  # 建议：整条流水线保持 lazy，最后再取 head
```

**错误 4：以为 explain() 已经把查询跑完了**
```python
plan_text = pipeline.explain()  # 只是计划文本
print(pipeline.collect())       # 真正的结果
```

**错误 5：布尔列过滤写成字符串比较**
```python
orders.filter(pl.col("refunded") == "False")  # 永远为 False
orders.filter(~pl.col("refunded"))            # 正确：取反
```
## 自检清单

- [ ] 三段结果都是 `.collect()` 之后的 DataFrame（打印出来是表格，不是计划文本）
- [ ] `filtered` 是 3722 行，且已退款订单全部被排除
- [ ] `region_stats` 按 `revenue` 降序，营收合计 4,968,434.34 元
- [ ] 能指着 `plan_text` 说出 `FILTER`、`AGGREGATE`、`SORT` 各在哪一层，以及投影下推省掉了哪些列
- [ ] 能解释「为什么每一步都 `collect()` 反而更慢」

## 下一步建议

完成本课后，建议继续：
- **Polars 与 DuckDB 组合工作流**：学习 Polars 清洗 + DuckDB SQL 分析的组合模式
- 在 Playground 中尝试用 `pipeline.explain()` 查看执行计划，理解 Polars 的优化策略
