# 工作区课程内容规范（v2，改版 M4 用）

> 面向写课程内容的人/代理。样例以 `learn_da/content/lessons/03-polars-groupby.md` 为准（已成标杆，先读它）。

## 1. 一次改动的产物

| 产物 | 路径 | 说明 |
|---|---|---|
| 课程正文 | `learn_da/content/lessons/NN-slug.md` | frontmatter 补 `workspace:` 块 + 正文加厚 |
| 参考解 | `learn_da/scripts/solutions/<slug 里的连字符换成下划线>.py` | `SOLUTIONS = {"c2": "...", "c3": "..."}`，只列 **task 格** |
| 数据集 | `learn_da/content/datasets/ecommerce/*.csv` | **只读**，绝不手改；要新数据就改 `scripts/build_datasets.py` 并重跑 |

`workspace:` 块写在 frontmatter 里、旧字段（`exercise`、`validator` 等）**保留不动**，位置放在 `exercise:` 之后、闭合 `---` 之前。

## 2. `workspace:` 骨架（照这个结构写）

```yaml
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
        # TODO: 按 region 分组，计算 revenue（amount 求和）与 orders（订单数），按 revenue 降序
        region_stats = orders
        print(region_stats)
  tasks:
    - id: t1
      title: 按区域聚合销售额
      cell: c2
      objective: |
        用 group_by('region') + agg 计算每个区域的 revenue 与订单数 orders，
        并按 revenue 降序排列；结果变量必须叫 region_stats。
      assertions:
        - id: t1-schema
          type: schema
          title: 结果包含 region / revenue / orders 三列
          var: region_stats
          columns: [region, revenue, orders]
```

### 字段规则

- `datasets`：可省略（纯 Python 课不需要数据）；写相对 `content/datasets/` 的路径，正斜杠。
- `cells[].id`：`c1`、`c2`… 顺序即执行顺序；`kind` ∈ `starter` / `task` / `scratch`。
- `kind: task` 的格必须有 `task_id`，且 `tasks[].cell` 指回它（一个任务一个格，不合并）。
- **不要写 `language: sql`** —— 沙箱会话只支持 python 格；DuckDB 课程一律 `import duckdb` 后用 `con.sql("...")` 写 SQL。
- `cells[].code` 用 `|` 块标量，相对 `workspace:` 缩进 8 空格；**每格最后都要 `print(...)`**，学员要看见结果。
- 任务数量：**2-3 个**（校验门槛 ≥2）；任务 id `t1`、`t2`…
- 每个任务 **2-4 条断言**。

## 3. 单元格代码约定

1. `c1` 永远是 starter：读数据 + 打印 `shape` / `head()`，学员点「运行」就能看到数据长什么样；**不得包含任务答案**。
2. 重放语义：所有格共享同一个命名空间，后面的格直接用前面格定义的变量（`orders`、`region_stats`…）。所以变量名要在任务 `objective` 里明确写出来，学员照着命名才能过断言。
3. task 格保留 `# TODO:` 注释说明要做什么，并留一个「占位赋值 + print」的骨架（如 `region_stats = orders`），让学员能直接跑出「未完成」的结果。
4. 数据路径一律 `data/ecommerce/xxx.csv`（沙箱把数据集挂到 `data/`）。
5. 禁止：`input()`、网络、随机、`datetime.now()`、写文件、`sys.exit`、`os`/`subprocess`。
6. `order_date` / `signup_date` / `launch_date` 读进来是 **字符串**，需要日期课时用 `.str.to_date("%Y-%m-%d")`。

## 4. 断言 DSL（四型，只能用这四种）

| type | 必填 | 语义 |
|---|---|---|
| `schema` | `var`、`columns` | `var` 的列**包含** `columns`；`exact: true` 时才要求完全一致（含顺序） |
| `expr_true` | `expr` | Python 表达式为真；可用命名空间里的变量 + `abs`/`round`/`sorted`/`len`/`sum` 等安全内建 |
| `frame_equal` | `var`、`ref` | 与 `content/expected/<ref>` 逐行逐列比对（parquet）；`rtol`/`atol` 控容差、`order_matters` 控顺序 |
| `sql_rows` | `query`、`ref` | 在 `connection`（默认 `con`）上执行 SQL，结果与 `content/expected/<ref>`（json，含 `columns`/`rows`）比对 |

规则：

- `id` 全局唯一，建议 `<taskId>-<语义>`，如 `t1-schema`、`t1-sorted`。
- `title` 写给学员看，会显示在断言列表里。
- 浮点不要精确相等：`frame_equal` 用 `rtol: 1e-6`，`expr_true` 用 `abs(x - y) < 1e-6`，或先 `round`。
- `expr` 里出现 `__`（双下划线）会被直接拒绝。
- 典型组合：`schema`（列名/列存在）+ `frame_equal`（整表数值）。
- 断言要**能区分对错**：只查 `height == 4` 而不查数值，等于放过算错的答案。
  聚合结果优先用 `frame_equal` 与参考结果比对，而不是把汇总数字手抄进 `expr`——
  手抄的数字换数据集就得重抄，而且「整列错值但 sum 恰好对得上」时抓不出来。

断言写法参考（都在 03 课里验证过）：

```yaml
- id: t1-schema
  type: schema
  var: region_stats
  columns: [region, revenue, orders]
- id: t1-sorted
  type: expr_true
  expr: "region_stats['revenue'].to_list() == sorted(region_stats['revenue'].to_list(), reverse=True)"
- id: t2-sum
  type: expr_true
  expr: "abs(region_share['share'].sum() - 1.0) < 1e-2"
```

## 5. 参考解文件

```python
"""`polars-basics` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": "selected = orders.select(['order_id', 'region'])\nprint(selected)\n",
    "c3": "...",
}
```

- 键 = task 格的 cell id；值 = 能通过该任务断言的**完整代码字符串**（可含 `print`）。
- 参考解会被依次注入前序格之后执行，所以可以直接用前面格定义的变量。
- 文件放在 `learn_da/scripts/solutions/`，文件名 = slug 把 `-` 换成 `_`（如 `polars_basics.py`）。

## 6. 正文加厚要求

保留原有一切有价值的讲解与示例，按下面的结构补齐（数据课目标 260-330 行，纯 Python 课 180-240 行）：

1. `# 标题`
2. `## 这节课解决什么问题` —— 用 ecommerce 数据集的真实业务问题开场（3-6 句），点明交付什么。
3. `## 你将用到的数据` —— 表格列出本课用到的列（列名 / 类型 / 含义）+ 数据规模 + 已知坑（如 `region` 有前后空格、`amount` 在脏表里是字符串）。
4. 原有概念章节与示例代码（保留，可小幅修订）。
5. `## 任务清单` —— 逐条列 `t1`/`t2`/`t3` 的验收标准，与 frontmatter 的 `objective` 一致；说明「右边工作区按顺序做，通过才解锁下一个」。
6. `## 常见坑` —— 原有错误示例 + 针对本数据集新增 1-2 条。
7. `## 自检清单` —— 3-5 条可勾选（- [ ] 形式）。
8. `## 下一步建议`（保留）。

**不要**在正文里给出任务格的完整可抄实现（设计稿 §7 明确要求正文是"场景说明书"）。原有教学示例保持通用小数据即可，改用数据集时不要直接等于任务答案。

## 7. 校验（必须自己跑通）

```bash
cd learn_da
.venv/Scripts/python.exe -m pytest tests/test_workspace_content.py -q -k "slug1 or slug2"
.venv/Scripts/python.exe scripts/content_lint.py
```

`test_workspace_content.py` 会验证：

- 起步代码在每个任务断言下**必须失败**（防白给）；
- 参考解在**完整重放**下每个任务断言**全过**；
- 数据集存在且总量 ≤ 2MB（必须 ≤ Runner 的 `RUNNER_SESSION_MAX_DATASET_BYTES`，否则能过 lint 却在运行时被拒）。

## 8. 已知坑

- YAML 标量里出现「冒号 + 空格」必须整体加双引号（如 `title: "字段：值"`），否则会被解析成映射并触发 fail-closed。
- frontmatter 用 `---` 闭合；正文里不要出现顶格 `---`（会被误认）。
- 文件按 UTF-8 保存，LF 行尾，不要在末尾留多余空行。
- `ref` 的路径**相对于 `content/expected/`**：写 `ref: 07-t2-channels.parquet`，
  不要写 `ref: expected/07-t2-channels.parquet`（会解析成 `expected/expected/...`）。
- 加了 `frame_equal` / `sql_rows` 之后必须跑 `python scripts/build_expected.py` 生成参考结果，
  并跑 `python scripts/build_expected.py --check` 确认与参考解一致；
  预期结果缺失时 `scripts/content_lint.py` 会直接报错（fail-closed）。

## 9. ecommerce 数据集字段字典

`orders.csv`（5000 行）

| 字段 | 类型 | 含义 |
|---|---|---|
| `order_id` | str | `O000001` 唯一 |
| `customer_id` | str | 关联 `customers.csv` |
| `product_id` | str | 关联 `products.csv` |
| `region` | str | 华东 / 华北 / 华南 / 西南 |
| `channel` | str | app / web / mini_program / offline |
| `quantity` | int | 1-5 |
| `unit_price` | float | 下单时单价快照 |
| `discount` | float | 0.8 / 0.85 / 0.9 / 1.0 |
| `amount` | float | `round(unit_price * quantity * discount, 2)` |
| `order_date` | str(date) | 2025-01-01 ~ 2025-12-31 |
| `refunded` | bool | 已退款约 4% |

`orders_dirty.csv`（1230 行，清洗课专用）：`discount`/`quantity` 有空值、`amount` 混入 `N/A`（整列读成 str）、`order_date` 出现 `2025/11/22` 斜杠格式、`region` 有前后空格、`channel` 有大写、整行重复 30 条（`order_id` 也重复）。

`customers.csv`（800 行）：`customer_id`、`name`、`city`、`region`、`segment`（新客/活跃/沉睡/高价值）、`signup_date`。

`products.csv`（120 行）：`product_id`、`category`（数码/家居/服饰/图书/食品）、`unit_price`、`cost`、`launch_date`。