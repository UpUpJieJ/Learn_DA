---
id: 5
slug: polars-cleaning
title: Polars 数据清洗
category: polars
difficulty: beginner
estimated_minutes: 30
order: 5
tags: [polars, cleaning, missing-values, 数据清洗]
prev_lesson:
  slug: polars-expressions
  title: Polars 表达式与列计算
next_lesson:
  slug: polars-joins
  title: Polars 连接与合并
practice_objective: >-
  掌握 Polars 中缺失值、重复值、类型转换的处理方法，
  能把一张"脏数据"清洗成可分析的干净表。
completion_criteria:
  - 用 null_count() 查看每列缺失数量
  - 用 fill_null() 填充缺失值（固定值或统计值）
  - 用 unique() 去重
  - 用 cast() 转换字段类型
  - 用 str.to_date() 解析日期字符串
# Phase 3: 建议系统元数据
track: polars_basics
prerequisites: ['polars-basics', 'polars-expressions']
recommended_next: ['polars-joins']
skill_tags: ['data_cleaning', 'missing_values', 'fill_null', 'cast', 'deduplication']
is_review_friendly: true
is_branch_point: false
workspace:
  datasets:
    - ecommerce/orders_dirty.csv
  cells:
    - id: c1
      kind: starter
      code: |
        import polars as pl

        dirty = pl.read_csv("data/ecommerce/orders_dirty.csv")
        print(dirty.shape)
        print(dirty.head(3))
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: 先统计每列缺失数（存成 null_counts），
        # 再把 discount 的缺失填成 1.0、quantity 的缺失填成 1，结果命名为 filled_orders
        null_counts = dirty.null_count()
        filled_orders = dirty
        print(filled_orders.head(3))
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 按 order_id 去重（保留第一条），再把 region 两端空格去掉、channel 统一小写，
        # 结果命名为 cleaned_text
        cleaned_text = filled_orders
        print(cleaned_text.shape)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 把 amount 转成 Float64（"N/A" 这类坏值按 null 处理），
        # 再把 order_date 的分隔符统一后转成日期类型，结果命名为 typed_orders
        typed_orders = cleaned_text
        print(typed_orders.schema)
  tasks:
    - id: t1
      title: 统计缺失并填充 discount / quantity
      cell: c2
      objective: |
        用 null_count() 统计整表每列缺失数并存成 null_counts(DataFrame)；
        再用 fill_null 把 discount 缺失填成 1.0、quantity 缺失填成 1，结果命名为 filled_orders。
      assertions:
        - id: t1-null-quantity
          type: expr_true
          title: null_counts 统计出 quantity 缺失 23 个
          expr: "null_counts['quantity'][0] == 23"
        - id: t1-null-discount
          type: expr_true
          title: null_counts 统计出 discount 缺失 33 个
          expr: "null_counts['discount'][0] == 33"
        - id: t1-null-left
          type: expr_true
          title: filled_orders 的 discount 与 quantity 已无缺失
          expr: "filled_orders['discount'].null_count() == 0 and filled_orders['quantity'].null_count() == 0"
        - id: t1-sum
          type: expr_true
          title: 填充后 discount 合计 1140.05、quantity 合计 2233（1230 行）
          expr: "filled_orders.height == 1230 and abs(filled_orders['discount'].sum() - 1140.05) < 0.01 and filled_orders['quantity'].sum() == 2233"
    - id: t2
      title: 按 order_id 去重并规范文本
      cell: c3
      objective: |
        用 unique(subset=["order_id"], keep="first") 去掉整行重复的订单；
        再把 region 两端空格去掉（str.strip_chars）、channel 统一小写（str.to_lowercase），
        结果命名为 cleaned_text。
      assertions:
        - id: t2-rows
          type: expr_true
          title: 去重后剩 1200 行
          expr: "cleaned_text.height == 1200"
        - id: t2-key
          type: expr_true
          title: order_id 不再重复
          expr: "cleaned_text['order_id'].n_unique() == cleaned_text.height"
        - id: t2-region
          type: expr_true
          title: region 只剩四个大区，且没有空格变体
          expr: "sorted(cleaned_text['region'].unique().to_list()) == ['华东', '华北', '华南', '西南']"
        - id: t2-channel
          type: expr_true
          title: channel 只剩四个小写取值
          expr: "sorted(cleaned_text['channel'].unique().to_list()) == ['app', 'mini_program', 'offline', 'web']"
    - id: t3
      title: 修金额与日期类型
      cell: c4
      objective: |
        用 cast(pl.Float64, strict=False) 把 amount 从字符串转成数值（"N/A" 变 null）；
        把 order_date 的分隔符统一后用 str.to_date 转成 Date 类型，结果命名为 typed_orders。
      assertions:
        - id: t3-schema
          type: schema
          title: amount 是 Float64、order_date 是 Date
          var: typed_orders
          columns: [order_id, amount, order_date]
          dtypes:
            amount: Float64
            order_date: Date
        - id: t3-amount-null
          type: expr_true
          title: amount 里 29 个坏值转成了 null，其余可计算
          expr: "typed_orders['amount'].null_count() == 29"
        - id: t3-date
          type: expr_true
          title: 日期全部解析成功，覆盖 2025 全年
          expr: "typed_orders['order_date'].null_count() == 0 and str(typed_orders['order_date'].min()) == '2025-01-01' and str(typed_orders['order_date'].max()) == '2025-12-31'"
        - id: t3-rows
          type: expr_true
          title: 类型修复不改变行数（1200）
          expr: "typed_orders.height == 1200"
---
# Polars 数据清洗

## 这节课解决什么问题

真实数据很少是干净的：折扣可能没填、件数可能没传、同一张订单被重写了两遍、大区名前后带空格、
渠道一侧写 `APP` 一侧写 `app`、金额列混进 `N/A`、日期一会儿 `-` 一会儿 `/`。

这些脏点会让每个数字都偏：`amount` 是字符串时 `sum()` 直接报错，`" 华东"` 会被算成另一个大区，重复订单去掉则 GMV 翻倍。

这一课用一张 1230 行的脏订单表练四类动作：**看缺失 → 填缺失 → 去重与文本规范化 → 类型修复（数值 / 日期）**，每步都保留行数对照。

## 你将用到的数据

工作区读的是 `data/ecommerce/orders_dirty.csv`（**1230 行 × 11 列**），它是 `orders.csv` 的"事故版"：

| 脏点 | 具体表现 | 用什么处理 |
|------|----------|------------|
| 缺失值 | `quantity` 缺 23 个、`discount` 缺 33 个 | `null_count()` / `fill_null()` |
| 重复行 | 30 条订单被整行重复写入（`order_id` 也重复） | `unique(subset=['order_id'])` |
| 文本脏 | `region` 前后带空格、`channel` 大小写混杂 | `str.strip_chars()` / `str.to_lowercase()` |
| 类型脏 | `amount` 是字符串且混有 `N/A`；`order_date` 混用 `-` 与 `/` | `cast(..., strict=False)` / `str.to_date()` |

已知的坑：

- 整表读进来时 `amount`、`order_date` 都是 **String**：`sum()` 报错既是坑也是提示。
- 业务口径要去的是"同一订单被写两遍"，所以去重要指定 `subset=['order_id']`，而不是裸 `unique()`。
- `str.replace("-", "/")` 只替换**第一个**匹配，`2025/11-05` 这类混合格式必须用 `str.replace_all`。
- `cast` 默认 `strict=True`，遇到 `N/A` 直接抛异常；`strict=False` 才会把它变成 `null`。

## Pandas → Polars 对照

| Pandas | Polars | 说明 |
|--------|--------|------|
| `df.isnull().sum()` | `df.null_count()` | 查看缺失数量 |
| `df.drop_duplicates(subset=['id'])` | `df.unique(subset=["id"], keep="first")` | 去重 |
| `pd.to_datetime(df['col'])` | `df.with_columns(pl.col('col').str.to_date(...))` | 日期解析 |

## 核心概念

清洗的顺序通常是：**先看 → 再补 → 再删 → 最后修类型**。常用方法：

- `null_count()`：每列缺失数量，返回 1 行 DataFrame，按列取 `[0]` 得到标量
- `fill_null(常量或表达式)`：填充空值，参数可以是 `1.0`，也可以是 `pl.col('x').mean()`
- `unique(subset=[...], keep='first')`：按关键字段去重；`cast(dtype, strict=False)`：坏值变 `null` 不报错

## 缺失值处理

```python
import polars as pl
df = pl.DataFrame({"city": ["北京", None, None, "上海"], "score": [88, None, None, 95]})
print(df.null_count())          # 每列缺几个
cleaned = df.with_columns(
    pl.col("city").fill_null("未知"),
    pl.col("score").fill_null(pl.col("score").mean()),
)
print(cleaned)
```

`fill_null(pl.col("score").mean())` 用该列均值填充——均值本身也被缺失值影响，想更稳就用 `median()`。
**填充规则一定要写注释**：`discount` 填 `1.0` 是"默认没打折"，填 `0` 意思完全不同，后续报表解释会全变。

## 文本规范化

```python
df.with_columns(
    pl.col("city").str.strip_chars(),      # 去掉两端空白
    pl.col("channel").str.to_lowercase(),  # APP / App → app
)
```

`strip_chars()` 不带参数时去掉首尾空白字符。分组统计前必须先规范化，否则同一个大区、同一个渠道会被
拆成多个取值——这类错误不会报错，只会让数字悄悄偏小。

## 类型修复与日期解析

```python
orders = pl.DataFrame({"order_date": ["2026-01-01", "2026/01/02"], "amount": ["100.5", "N/A"]})

fixed = orders.with_columns(
    pl.col("amount").cast(pl.Float64, strict=False),   # "N/A" → null
    pl.col("order_date").str.replace_all("-", "/"),     # 统一分隔符
).with_columns(
    pl.col("order_date").str.to_date("%Y/%m/%d"),       # 再解析成 Date
)
print(fixed.schema)
```

这里是**两次** `with_columns`：同一批表达式不能引用刚算出来的列，日期必须先统一分隔符再解析。
解析失败会抛错，所以格式串要与实际字符串完全一致（这里用 `%Y/%m/%d`）。

## 练习

下面这张小表把四个动作串起来，跑一遍看清每步行数怎么变：

```python:example
import polars as pl
raw = pl.DataFrame({
    "user_id": [1, 2, 2, 3, 4, 5],
    "city": [" 北京", None, None, "上海 ", "深圳", None],
    "signup_date": ["2026-01-01", "2026-01-03", "2026-01-03", "abc", "2026/01/10", "2026/01/12"],
    "age": ["25", "30", "30", "22", "unknown", "28"],
})
print(raw.null_count())
cleaned = (
    raw.unique(subset=["user_id"], keep="first")
    .with_columns(
        pl.col("city").str.strip_chars().fill_null("未知"),
        pl.col("age").cast(pl.Int32, strict=False),
        pl.col("signup_date").str.replace_all("-", "/"),
    )
    .with_columns(pl.col("signup_date").str.to_date("%Y/%m/%d", strict=False))
)
print(cleaned.sort("user_id"))
print(cleaned.null_count())
```

这是**通用小例子**：工作区换成 1230 行脏表（多出重复 + 空格 + 大小写 + `N/A`），动作与顺序一样，变量名按任务说明来。

## 任务清单

右边工作区按顺序做：**当前任务的断言全部通过才解锁下一个**。三个任务共享同一个命名空间。

- **t1 统计缺失并填充 discount / quantity**（c2）：产出 `null_counts` 与 `filled_orders`。
  `discount` 缺失填 `1.0`、`quantity` 缺失填 `1`；验收比对两列缺失数、填充后合计与行数——填错默认值就过不了。
- **t2 按 order_id 去重并规范文本**（c3）：产出 `cleaned_text`。按 `order_id` 保留第一条，
  `region` 去两端空格、`channel` 统一小写；验收看行数（1200）、主键唯一性与两组取值的精确集合。
- **t3 修金额与日期类型**（c4）：产出 `typed_orders`；`amount` 用 `cast(pl.Float64, strict=False)` 让 `N/A` 变 `null`，`order_date` 统一分隔符后转 `Date`；验收比对 `schema`、坏值个数与日期范围。

## 常见错误

**错误 1：unique 忘记 subset，cast 前不处理脏字符串**
```python
df.unique()                                    # 只有整行完全相同才算重复
df.unique(subset=["order_id"], keep="first")   # 按业务主键去重
df.with_columns(pl.col("amount").cast(pl.Float64))                 # "N/A" 抛异常
df.with_columns(pl.col("amount").cast(pl.Float64, strict=False))   # 坏值变 null
df.fill_null("未知")                     # 错：df 没变，results 被丢掉
df = df.fill_null("未知")                # 正确：接住返回值
```

**错误 2（本数据集特有）：`str.replace` 只替换第一处**
```python
pl.col("order_date").str.replace("-", "/")      # 错：2025/11-05 还剩一个 "-"
pl.col("order_date").str.replace_all("-", "/")  # 正确
```

## 自检清单

- [ ] 我能说出 `null_count()` 返回什么形状，以及为什么用 `[0]` 取标量
- [ ] 填充用的默认值（`discount=1.0`、`quantity=1`）能一句话说清业务含义
- [ ] 去重指定了 `subset=['order_id']` 与 `keep='first'`，而不是裸 `unique()`
- [ ] 日期转 `Date` 前用 `replace_all` 统一了分隔符，解析后无 null，行数从 1230 变 1200

## 下一步建议

- **Polars 连接与合并**：学习如何把多张表拼在一起；也可在 Playground 中处理一份有缺失值的 CSV 练手
