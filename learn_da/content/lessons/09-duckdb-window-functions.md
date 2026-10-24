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
            "CREATE TABLE orders AS "
            "SELECT * FROM read_csv_auto('data/ecommerce/orders.csv')"
        )
        print(con.sql("SELECT COUNT(*) AS orders, COUNT(DISTINCT region) AS regions FROM orders").fetchall())
        print(con.sql("SELECT * FROM orders LIMIT 3").fetchall())
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: 用 RANK() OVER (PARTITION BY region ORDER BY amount DESC)
        # 给每个区域内的订单按金额排名，查出 order_id / region / amount / amount_rank，
        # 按 region、amount_rank 排序
        region_rank = []
        print(region_rank)
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 用 SUM(amount) OVER (PARTITION BY region ORDER BY order_date)
        # 算每个区域截至当日的累计销售额，查出 region / order_date / amount / running_amount
        region_running = []
        print(region_running)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: group_rows 用 GROUP BY region 汇总 revenue 与订单数；
        # window_rows 用 SUM(amount) OVER (PARTITION BY region) 保留全部明细行，
        # 两边的区域销售额要对得上
        group_rows = []
        window_rows = []
        print(group_rows, len(window_rows))
  tasks:
    - id: t1
      title: 组内金额排名
      cell: c2
      objective: |
        用 RANK() OVER (PARTITION BY region ORDER BY amount DESC) 计算每个区域内的金额排名，
        查出 order_id、region、amount、amount_rank 四列并按 region、amount_rank 排序，
        结果变量叫 region_rank。
      assertions:
        - id: t1-rows
          type: expr_true
          title: 窗口函数不折叠行，结果仍是 5000 行
          expr: "len(region_rank) == 5000"
        - id: t1-ties
          type: expr_true
          title: 每个区域最高金额并列时 RANK 给相同名次（第 1 名共 5 行）
          expr: "sorted(round(r[2], 2) for r in region_rank if r[3] == 1) == [15389.44, 15389.44, 18298.95, 18298.95, 19236.8]"
        - id: t1-partition
          type: expr_true
          title: 4 个区域各自都有第 1 名（说明是分区排名而不是全表排名）
          expr: "sorted({r[1] for r in region_rank if r[3] == 1}) == sorted({r[1] for r in region_rank})"
    - id: t2
      title: 区域累计销售额
      cell: c3
      objective: |
        用 SUM(amount) OVER (PARTITION BY region ORDER BY order_date) 计算区域累计销售额，
        查出 region、order_date、amount、running_amount 四列并按 region、order_date 排序，
        结果变量叫 region_running。
      assertions:
        - id: t2-rows
          type: expr_true
          title: 累计查询仍保留 5000 行明细
          expr: "len(region_running) == 5000"
        - id: t2-final
          type: expr_true
          title: 每个区域的最大累计值等于该区域全年销售额
          expr: "abs(max(r[3] for r in region_running if r[0] == '华东') - 1220641.6) < 0.05 and abs(max(r[3] for r in region_running if r[0] == '华北') - 1395335.55) < 0.05 and abs(max(r[3] for r in region_running if r[0] == '华南') - 1368599.41) < 0.05 and abs(max(r[3] for r in region_running if r[0] == '西南') - 1303267.3) < 0.05"
        - id: t2-start
          type: expr_true
          title: 累计值从小开始（是按日期累加，不是整组总额）
          expr: "min(r[3] for r in region_running) < 2000"
    - id: t3
      title: 窗口函数与 GROUP BY 的行数对比
      cell: c4
      objective: |
        用 GROUP BY region 汇总出 group_rows（region、revenue、订单数），
        再用 SUM(amount) OVER (PARTITION BY region) 得到 window_rows（order_id、region、amount、region_revenue）；
        两边区域销售额必须一致，但行数是 4 与 5000。
      assertions:
        - id: t3-rows
          type: expr_true
          title: GROUP BY 折叠成 4 行，窗口查询保留 5000 行
          expr: "len(group_rows) == 4 and len(window_rows) == 5000"
        - id: t3-match
          type: expr_true
          title: 窗口算出的区域销售额与 GROUP BY 结果一致
          expr: "sorted(round(r[1], 2) for r in group_rows) == sorted({round(r[3], 2) for r in window_rows})"
        - id: t3-regions
          type: expr_true
          title: 两张结果的区域集合相同
          expr: "sorted(r[0] for r in group_rows) == sorted({r[1] for r in window_rows})"
---

# DuckDB 窗口函数

## 这节课解决什么问题

`orders.csv` 的 5000 笔订单分布在四个区域（华东 1249、华北 1308、华南 1181、西南 1262）。运营方现在要三样东西：**每个区域内部的金额排名**（用来挑头部订单做回访）、**区域累计销售额曲线**（看全年是怎么累起来的），以及一个绕不开的疑问——**窗口函数会不会像 `GROUP BY` 那样把明细行折叠掉**。

这三个问题都要在保留 5000 行明细的前提下回答，所以 `GROUP BY` 只能解决一半。窗口函数 `FUNC() OVER (PARTITION BY ... ORDER BY ...)` 的定位就是「分组算完再贴回每一行」。本课你会在同一张订单表上写出组内排名、区域累计、以及一份「窗口 vs GROUP BY」的对照结果。

## 你将用到的数据

`data/ecommerce/orders.csv`（5000 行，11 列，本课只用到下面几列）

| 字段 | 类型 | 含义 |
|---|---|---|
| `order_id` | str | `O000001` 形式的订单号，唯一 |
| `region` | str | 下单区域：华东 / 华北 / 华南 / 西南 |
| `amount` | float | 订单实付金额（已含数量与折扣） |
| `order_date` | date | 2025-01-01 ~ 2025-12-31 |

已知坑：

- `read_csv_auto` 会把 `order_date` 读成 **DATE** 类型，`ORDER BY order_date` 是按日期排，不是按字符串排。
- 同一天有多笔订单。`ORDER BY order_date` 会让这些行处在同一「并列组」里，默认的 `RANGE` 帧会把同一天的行一起计入累计——这不是 bug，是 SQL 标准行为。
- `amount` 是 `DOUBLE`，核对总数时用 `round(..., 2)` 或比较差值，不要写 `= 1220641.6`。
- 区域销售额合计：华东 1220641.60、华北 1395335.55、华南 1368599.41、西南 1303267.30，全表 5287843.86。

## GROUP BY vs 窗口函数

| 特性 | GROUP BY | 窗口函数 |
|------|----------|----------|
| 结果行数 | 减少（每组一行） | 不变（保留所有明细行） |
| 典型用途 | 汇总统计 | 组内排名、累计值、占比 |
| 语法 | `GROUP BY col` | `FUNC() OVER (PARTITION BY col ORDER BY col)` |

一句话：`GROUP BY` 折叠行，窗口函数把分组计算结果**贴回每一行**——`PARTITION BY` 相当于分组，`ORDER BY` 决定窗口帧怎么推进（省略 `PARTITION BY` 就是整表一个窗口，下面的「常见坑」会讲为什么这是最常见的错误）。
## 给每个区域内订单排名

```python:example
import duckdb

con = duckdb.connect()
con.execute("""
    CREATE TABLE orders AS SELECT * FROM (VALUES
        (1, '华东', '2026-01-01', 120), (2, '华东', '2026-01-02', 300),
        (3, '华东', '2026-01-03', 180), (4, '华南', '2026-01-01', 90),
        (5, '华南', '2026-01-02', 260)
    ) AS t(order_id, region, order_date, amount)
""")

result = con.execute("""
    SELECT order_id, region, order_date, amount,
           RANK() OVER (PARTITION BY region ORDER BY amount DESC) AS amount_rank,
           SUM(amount) OVER (PARTITION BY region ORDER BY order_date) AS running_amount
    FROM orders
    ORDER BY region, order_date
""").fetchall()

print(result)
```
## 常见窗口函数

| 函数 | 说明 | 示例场景 |
|------|------|----------|
| `ROW_NUMBER()` | 连续编号，不并列（1, 2, 3, 4） | 给每行一个唯一序号 |
| `RANK()` | 排名，相同值并列并跳号（1, 2, 2, 4） | 销售额排名 |
| `DENSE_RANK()` | 排名，相同值并列不跳号（1, 2, 2, 3） | 成绩排名 |
| `SUM(...) OVER (...)` | 累计值或分组总值 | 累计销售额 |
| `AVG(...) OVER (...)` | 窗口平均值 | 组内平均 |
## ORDER BY 决定「帧」：从总额到累计

同一个 `SUM(...) OVER (...)`，加不加 `ORDER BY` 结果完全不同：

```sql
-- 整组总额：分区内每一行都拿到同一个数
SUM(amount) OVER (PARTITION BY region)

-- 截至当前行：默认帧是 RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW，
-- 同一天的并列行会拿到相同的累计值
SUM(amount) OVER (PARTITION BY region ORDER BY order_date)

-- 严格逐行累加（并列也一行一行推进），需要显式指定 ROWS 帧
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY order_date, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

理解这一点，你就能一眼看出「为什么每条明细行都有一个不一样的累计值」以及「为什么同一天的两笔订单累计值相同」。

## 动手练

上文那格示例里的 5 行 `orders` 小表和两份窗口计算，值得亲手改三处再跑一遍：

- 把 `RANK()` 换成 `ROW_NUMBER()`，看华东那两笔 120 / 300 的名次是否变化；
- 删掉 `SUM(...)` 里的 `ORDER BY order_date`，`running_amount` 会变成整个区域的总额；
- 用 CTE 把排名结果包一层，再 `WHERE amount_rank = 1`，体会窗口函数为什么不能直接写在 `WHERE` 里。
## 任务清单

右边工作区按 `c1 → c2 → c3 → c4` 顺序执行，**当前任务通过后才解锁下一个**。`c1` 已经用 `read_csv_auto` 把 CSV 建成 `orders` 表，后面三格都在同一个 `con` 上写 SQL。

| 任务 | 单元格 | 要交付的变量 | 验收标准 |
|---|---|---|---|
| `t1` 组内金额排名 | `c2` | `region_rank` | 5000 行明细、第 1 名共 5 行（华东最高金额并列）、四个区域各有第 1 名 |
| `t2` 区域累计销售额 | `c3` | `region_running` | 5000 行、累计从小额开始（不是整组总额）、每个区域的最大累计值等于该区域全年总额 |
| `t3` 窗口 vs GROUP BY | `c4` | `group_rows` / `window_rows` | 4 行对 5000 行、区域销售额两边一致、区域集合相同 |

排名里那个「第 1 名 5 行」不是数据错误：华东有两笔订单金额同时是 15389.44，`RANK()` 会给它们相同名次并跳过下一个名次。如果你写成了 `ROW_NUMBER()`，只会剩下 4 行——正好说明两者的区别。

## 常见坑

**错误 1：忘记 PARTITION BY，排名变成全局**
```sql
RANK() OVER (ORDER BY amount DESC)                      -- 错误：所有订单混在一起排
RANK() OVER (PARTITION BY region ORDER BY amount DESC)   -- 正确：按区域分组
```

**错误 2：在 WHERE 中过滤窗口函数**
```sql
-- WHERE 里不能直接写窗口函数，用 CTE 包一层
WITH ranked AS (SELECT *, RANK() OVER (...) AS rnk FROM orders)
SELECT * FROM ranked WHERE rnk = 1
```

**错误 3：混淆 RANK 和 ROW_NUMBER**
```sql
-- RANK：相同值并列会跳号（1, 2, 2, 4）；ROW_NUMBER：强制不并列（1, 2, 3, 4）
```

**错误 4：结果「看起来对」其实漏了分区**
```sql
-- 行数还是 5000，但只有 1 行是第 1 名；检查办法：每个区域都该有自己的第 1 名
SELECT region, MIN(amount_rank) FROM ranked GROUP BY region
```

**错误 5：用等号核对 DOUBLE 金额**
```sql
SELECT SUM(amount) FROM orders WHERE region = '华东';  -- 1220641.5999999999，别写 =
```
## 自检清单

- [ ] 每条窗口查询的结果行数都是 5000（没有被折叠）
- [ ] 四个区域各自都有 `amount_rank = 1` 的行
- [ ] 累计销售额的末行等于该区域的全年总额，首行明显小于总额
- [ ] 能说出「不加 ORDER BY」和「加 ORDER BY」时 `SUM(...) OVER (...)` 的区别
- [ ] 核对金额时用 `round(..., 2)` 或差值，而不是 `=`

## 下一步建议

完成本课后，建议继续：
- **Polars 惰性流水线**：学习 Polars 的 lazy 模式，对比窗口函数在 Polars 中的写法（`over()`）
- 在 Playground 中尝试用窗口函数计算"每个品类的销售额占比"
