# 学习工作区重设计：Workspace + Task + Assertion + Coach

> 状态：设计稿（未开工）。日期：2026-10-21。
> 相关现状：`learn_da/app/practice/validator.py`、`learn_da/app/agent/evidence.py`、
> `learn_da/app/playground/schemas.py`、`learn_da_vue/src/views/Playground.vue`、
> `learn_da_vue/src/views/LessonDetail.vue`、`learn_da_vue/src/components/agent/AgentPanel.vue`。

## 0. 已定决策（2026-10-21，用户确认）

| # | 决策 | 选择 | 含义 |
|---|---|---|---|
| D1 | 执行模型 | **重放式多 cell** | 每次执行从第 1 格顺序重放到目标格，单进程、用完即弃；不做常驻 kernel（留作后续阶段，接口不变） |
| D2 | 数据来源 | **先自造**，后期可导真实数据 | 课程自带只读数据集（`content/datasets/`），用固定随机种子生成、随课程入库与 lint |
| D3 | 执行顺序语义 | **严格按任务顺序**（响应式） | 改上游格 → 下游全部标记 stale，相关任务判定作废需复核；不允许"用旧状态过关" |
| D4 | 交互细节（6 项） | 全部按建议采纳 | 允许草稿格；保留简化 Playground 作自由沙盒；允许跳过任务（记 `skipped`）；数据先干净后加脏；灰度期两套入口并存；样板课先做 `03-polars-groupby` |

三条决策相互强化：严格顺序让重放式成为**语义等价**方案（因为状态就是"从头跑到这里"），
不需要 kernel 也能保证一致性；自造数据集则让重放可复现（同一份只读数据、同一种子）。

## 1. 问题（现状证据）

1. **执行器**：`POST /api/v1/playground/execute` 收 `{code, language, lessonSlug?, exerciseId?}`
   （`learn_da/app/playground/schemas.py:18-27`），跑完整个脚本返回 stdout；
   每次独立进程、无状态、无 cell 概念。
2. **判定**：白名单三种（`learn_da/app/practice/validator.py:69-74`）
   `stdout_exact` / `stdout_contains` / `dataframe_rows`——全是"输出与答案的字符串/行比对"。
   例：`polars-groupby` 只校验 `columns` 与 `row_count`，**数值全错也能通过**。
3. **课程**：13 课 × 1 题；数据内联在 starter 里（`learn_da/content/lessons/03-polars-groupby.md:34-39`），
   `read_csv/read_parquet/read_json` 在全部课程中**零出现**，所谓"数据分析"实际是构造 6 行字面量。
4. **AI**：证据只有"最近一次 attempt 的 stdout/stderr 各截断 500 字符"（`learn_da/app/agent/evidence.py:46-63`），
   五态枚举 + `hintLevel` 由求助次数估算（`learn_da/app/agent/service.py:_resolve_hint_level`），
   看不见过程、看不见卡点；工具仅 4 个只读函数（`learn_da/app/agent/fc_tools.py:29-92`）。
5. **前端**：`Playground.vue` 1442 行、`LessonDetail.vue` 1095 行、`AgentPanel.vue` 808 行，
   三种"代码"（正文示例、练习 starter、AI 代码块）互不相通，靠复制/注入搬运。

根因：AI、课程、执行器之间共享的数据只有"一条 lesson slug + 一次 stdout"。

## 2. 目标与非目标

**目标**

- G1 学习者在一个**有状态工作区**里完成 3-6 个递进任务，像做真实数据分析。
- G2 判定基于**可执行断言**（变量状态），失败返回结构化诊断（哪条断言、实际 vs 期望）。
- G3 AI 拥有**会话级上下文**（任务、cell、轨迹、断言失败明细），能做三档介入与可应用动作。
- G4 严格顺序 + 重放，保证"通过"始终可复现、可回归测试。
- G5 课程标准可 lint：starter 必 fail、参考解必 pass、数据集与断言一致。

**非目标（本期不做）**

- 常驻 kernel / 真增量执行（M5 再议）。
- 账号体系（继续匿名签名 cookie）。
- 任意用户自建课程 / 共享会话。
- 沙箱网络访问（保持无网络 fail-closed 策略）。

## 3. 核心概念与语义

| 概念 | 定义 | 关键约束 |
|---|---|---|
| Lesson | 一课：场景说明 + 任务序列 + 数据集引用 | 至少 3 个 task |
| Scenario | 场景文本（真实业务口吻），是课程正文的主体 | 引用数据集里的真实字段 |
| Dataset | 随课程入库的只读数据文件 | 每课 ≤ 5MB，路径固定为 `data/<name>` |
| Task | 一个递进目标：`goal` + `assertions` + `hints` | id 形如 `t1`、`t2`，顺序即依赖 |
| Cell | 工作区一格代码，归属某 task 或 `scratch` | 有稳定 `cell_id`、`seq` |
| RunEvent | 一次执行记录（代码哈希、状态、输出、耗时） | 幂等键 `request_id` |
| Assertion | 可执行断言，运行在用户命名空间里 | 只读、超时受限、不修改状态 |
| TaskAttempt | 一次"提交判定"结果（含逐条断言结果） | 通过后若上游变更即置 stale |
| HintUsage | 提示阶梯使用记录（第几层、谁触发） | 服务端记账，不允许越层重放 |
| Session | 学习者在某课的会话：cell 列表 + 任务状态 | 每人每课一个活跃会话 |

### 3.1 严格顺序（响应式）语义

```
任务 t1 → t2 → t3；每任务一个提交格（可加 scratch 草稿格）
编辑 cell_k（seq = k）:
  - 该格状态 -> dirty
  - 所有 seq > k 的 cell -> stale（保留代码与历史输出，但标记"需重跑"）
  - 所有依赖 stale cell 的 TaskAttempt -> 从 passed 降级为 stale（"需复核"）
  - 已完成任务的下游任务 -> 重新锁定（未解锁），直到上游重新通过
执行 cell_k:
  - 服务端重放 seq 1..k（全新进程、同一份只读数据）
  - 若任一前序格失败 -> 本次结果 = upstream_failed（不写断言结论）
  - 否则逐条评估该格所属 task 的断言 -> passed / failed
提交 task（显式动作）:
  - 仅当该 task 的提交格最近一次运行 passed 且无 stale 上游时才允许
  - 写入 TaskAttempt，解锁下一个 task
```

不允许的行为（服务端硬约束）：

- 跳格执行（只跑第 5 格而前面是 stale）→ 拒绝，返回 `prefix_stale`；
- 用扫描/篡改的方式改数据文件 → 只读挂载；
- 未通过就解锁下一 task → 拒绝（可显式"跳过"，但记录 `skipped`，不计完成）。

### 3.2 重放算法（v1）

```python
def run_cell(session, cell_id, request_id) -> RunResult:
    cells = session.cells_ordered_up_to(cell_id)      # 含目标格
    program = [c.code for c in cells]
    result = runner.execute_session(
        program=[...],                                 # 逐格执行，隔离 stdout 归属
        datasets=lesson.datasets,                      # 只读挂载 data/
        assertions=task.assertions_for(cell_id),       # 仅目标格断言
        limits={timeout_s: 10, max_output: 65536, memory_mb: 512},
    )
    return RunResult(
        cells=[CellRun(status, stdout, stderr, duration_ms) for each],
        assertions=result.assertions,
        prefix_hash=hash(cells),
    )
```

成本控制：

- 每课前缀总时长目标 **< 3s**（自造数据集 ≤ 5000 行，`read_csv` < 100ms）；
- 超时按**整次重放**计（默认 10s），不是按格；
- 未改变的前缀不缓存（重放模式下无缓存），但前端"只跑改动格"仍表现为一次重放。

未来（M5）升级为常驻 kernel 时，仅替换 `runner.execute_session` 的实现，
`prefix_hash` 变成 kernel 命中的键，API 与数据模型不变。

## 4. 数据模型（新增表）

```python
lesson_sessions
  id, visitor_id, lesson_slug, status[active|completed|abandoned],
  active_task_id, created_time, updated_time
  UNIQUE(visitor_id, lesson_slug)

session_cells
  id, session_id, task_id(NULL=scratch), seq, language[python|sql],
  code TEXT, code_hash, created_time, updated_time
  INDEX(session_id, seq)

run_events
  id, visitor_id, session_id, cell_id, request_id, prefix_hash,
  execution_status[success|error|timeout|rejected|unavailable|upstream_failed],
  stdout, stderr, error_type, duration_ms, assertions_json, created_time
  UNIQUE(visitor_id, request_id)          # 幂等（沿用 exercise_attempts 的做法）

task_attempts
  id, visitor_id, session_id, task_id, cell_id, run_event_id,
  verdict[passed|failed|skipped|stale], assertion_results JSON, created_time
  INDEX(visitor_id, task_id)

hint_usages
  id, visitor_id, session_id, task_id, level INT, source[auto|requested],
  created_time
```

**legacy**：`exercise_attempts` 冻结为只读历史（不再写入新数据），保留表与索引，
旧页面下线后按需归档。`CodeSnapshot` 等死表同前（已在 2026-08-21 停止读取）。

## 5. API 契约

统一走 `StdResp` 包装，匿名签名 cookie 提供 `visitor_id`（服务端注入，不接受客户端参数）。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/workspace/sessions` | `{lessonSlug}`：创建或恢复活跃会话，返回 session + cells + taskStates |
| GET | `/api/v1/workspace/sessions/{id}` | 读取会话全量（含每格最近 RunEvent 摘要、任务状态） |
| PUT | `/api/v1/workspace/sessions/{id}/cells/{cellId}` | `{code}`：保存并触发下游 stale |
| POST | `/api/v1/workspace/sessions/{id}/cells/{cellId}/run` | `{requestId}`：重放执行 + 断言，返回逐格结果与任务判定 |
| POST | `/api/v1/workspace/sessions/{id}/tasks/{taskId}/submit` | `{requestId}`：显式提交（幂等），解锁下一任务 |
| POST | `/api/v1/workspace/sessions/{id}/tasks/{taskId}/hint` | `{}`：按服务端计算的层返回下一层提示并记账 |
| POST | `/api/v1/workspace/sessions/{id}/cells` | `{afterSeq, language}`：插入 scratch 草稿格 |
| DELETE | `/api/v1/workspace/sessions/{id}/cells/{cellId}` | 删除 scratch 格（提交格不可删） |

响应片段（`run`）：

```json
{
  "data": {
    "cells": [
      {"cellId": 12, "status": "success", "durationMs": 41, "stdoutTail": "…"},
      {"cellId": 13, "status": "error", "errorType": "NameError",
       "stderrFirstLine": "name 'ordrs' is not defined"}
    ],
    "assertions": [
      {"id": "a1", "ok": false, "title": "列名与顺序",
       "expected": ["region", "total_amount", "order_count"],
       "actual": ["region", "total", "cnt"],
       "message": "聚合列需要用 alias 命名为 total_amount / order_count"}
    ],
    "verdict": "failed",
    "taskState": {"taskId": "t2", "status": "failed", "attemptNo": 3}
  }
}
```

## 6. 断言 DSL（v2）

断言在 **Runner 进程内、用户命名空间里**执行（因为需要读变量），断言文本由服务端下发，
结果回传为结构化 JSON。类型限定四种：

```yaml
assertions:
  - id: a1
    type: expr_true           # 任意 Python 表达式，truthy 即通过
    expr: "region_stats.height == 5"
    title: 区域数应为 5
    on_fail: 用 orders['region'].n_unique() 对照一下

  - id: a2
    type: frame_equal         # 与参考结果逐值比对（polars/pandas 均可）
    var: region_stats
    ref: expected/03-t2-region.parquet   # 服务端内存注入，不落用户可见路径
    order_matters: true
    rtol: 1e-6
    title: 聚合结果与参考一致

  - id: a3
    type: schema              # 列名/类型校验
    var: orders
    columns: [order_id, region, product_id, amount, order_date]
    dtypes: {amount: Float64, order_date: Date}

  - id: a4
    type: sql_rows            # DuckDB 单元格：预期结果集比对
    query: "SELECT region, SUM(amount) FROM orders GROUP BY 1"
    ref: expected/07-t1.sql.json
```

约定：

- `schema` 的 `columns` 默认是**包含**语义（列出必须存在的列，多出来的列不判错）；
  加上 `exact: true` 才要求列顺序与集合完全一致——课程里校验"输出就这几列"时用它。
  `dtypes` 只校验列出的列，类型名大小写不敏感（`Float64` / `float64` 等价）。
- 断言**只读**：`expr_true` 在受限命名空间求值，禁止 `import`、文件写入（白名单 builtins）；
- 断言失败必须给 `actual`（`repr`，截断 500 字符），这是"结构化诊断"的来源；
- 单条断言超时 500ms，整体断言预算 2s；
- **弱保证说明**：`ref` 数据以内存注入不落盘，但用户代码与断言同进程，理论上可读父进程内存。
  威胁模型取"防误用不防恶意"：靠 RunEvent/TaskAttempt 记录与课程难度，不做强隔离。

### 6.1 与旧 validator 的关系

旧三型保留一个迁移期：新课程用 v2 断言，旧课程（13 课）在迁移完成前继续走
`exercise_attempts` + 旧 validator。`dataframe_rows` 作为 `frame_equal` 的退化子集，
在迁移完成后可下线（保留函数与测试若干版本，标注 deprecated）。

## 7. 内容格式 v2

```
learn_da/content/
  catalog.yml
  lessons/03-polars-groupby.md            # frontmatter + 场景正文
  datasets/ecommerce/{orders.csv,customers.csv,products.csv,README.md}
  expected/03-polars-groupby/{t2-region.parquet}
```

frontmatter 增量（旧字段保留，`exercise` 标记 deprecated）：

```yaml
workspace:
  datasets:
    - ecommerce/orders.csv
    - ecommerce/products.csv
  mount: data                 # 沙箱内挂载点
tasks:
  - id: t1
    title: 读入并确认数据
    goal: 把订单表读进 orders，确认 5000 行与关键列类型
    language: python
    starter: |
      import polars as pl
      # TODO: 读入 data/orders.csv
      orders = None
    assertions: [ ... ]
    hints:
      - level: 1
        text: 先 pl.read_csv("data/orders.csv")
      - level: 2
        text: 用 orders.schema 看类型，注意 amount 可能被读成 str
      - level: 3
        text: pl.read_csv(..., schema_overrides={"amount": pl.Float64})
  - id: t2
    title: 按区域聚合
    ...
```

正文（markdown）改为"场景说明书"：字段含义、业务问题、验收标准、必要的概念卡；
不再包含"照抄就能过"的完整参考实现（参考解只用于 lint 与断言 ref）。

**lint 规则（扩展 `scripts/content_lint.py`）**

| 规则 | 说明 |
|---|---|
| L1 | task 数 ≥ 3，id 唯一且按序 |
| L2 | 每 task 至少 1 条断言，且断言引用的 `var` 在参考解执行后存在 |
| L3 | starter 在该 task 断言下**必须 fail**（防白给） |
| L4 | 参考解在**完整序列**下全部 pass（重放语义下验证，防"单格通过、整链失败"） |
| L5 | hints 层数 ≥ 2 且非空；层号严格递增 |
| L6 | datasets 存在、总大小 ≤ 5MB、扩展名白名单（csv/parquet/json）、无 URL 引用 |
| L7 | `expected/*` 与断言 `ref` 一一对应；由数据集脚本可复现生成 |
| L8 | 场景正文引用的列名在数据集 schema 中存在 |

数据集生成脚本 `scripts/build_datasets.py`：固定 `random.seed`，可重跑得到字节一致的产物，
CI/本地都能校验 hash（与 L7 配合，避免"expected 与数据悄悄漂移"）。

## 8. 教练（Coach）集成

### 8.1 上下文

`POST /api/v1/agent/chat` 的 `context` 扩展（保持向后兼容，旧字段仍可用）：

```json
{
  "currentLesson": "polars-groupby",
  "taskId": "t2",
  "sessionId": 41,
  "cellId": 13,
  "currentCode": "…",
  "recentRuns": [
    {"cellId": 13, "status": "error", "errorType": "ColumnNotFoundError",
     "stderrFirstLine": "unable to find column \"total\"; valid columns: […]"},
    {"cellId": 13, "status": "success", "assertionsFailed": ["a2"]}
  ],
  "hintUsage": {"t2": 1}
}
```

服务端仍以**数据库为准**（session/run_events/task_attempts），客户端上下文只用于定位。
`evidence.py` 的五态保留为"执行/验证状态"子集，新增 `task_failed` / `task_passed` /
`upstream_failed` 三个 task 级状态。

### 8.2 三档介入

| 档位 | 触发 | 表现 | 记录 |
|---|---|---|---|
| ambient（环境提示） | 执行失败或断言失败后 1 次 | 教练面板出现一条折叠卡片「我看到了什么」：错误类型 + 断言差异 + 一句引导 | 不写 HintUsage |
| ladder（提示阶梯） | 用户点「给点提示」 | 服务端算层（失败次数 + 已用层）返回下一层，越层请求无效 | 写 HintUsage |
| chat（自由问答） | 用户提问 | 带完整上下文回答 | 记 AgentInteraction |

**层数计算（服务端权威）**：

```
level = min(3, 1 + failures_since_last_hint + hints_used)
```

失败次数来自 task_attempts（同 task、本次 hint 之后），不受客户端 history 影响。

### 8.3 可应用动作（propose → 用户确认）

模型输出末尾允许带一个结构化块（服务端校验后转成动作，不直接改代码）：

```json
{"action": "replace_cell", "cellId": 13, "code": "region_stats = orders.group_by('region').agg(...)",
 "reason": "你的聚合列没有 alias，断言 a1 不通过"}
```

前端渲染为 diff + 按钮「应用到第 3 格并重跑」；用户点确认才 `PUT cell` + `run`。
服务端只接受白名单动作（`replace_cell` / `insert_scratch_cell` / `run_cell`），
并校验目标 cell 属于当前会话与该 visitor。

## 9. 前端信息架构

```
┌──────────────────────────────────────────────────────────────┐
│ 课程头：title / 进度（t1 ✓ t2 ● t3 ○）/ 退出                    │
├──────────────┬───────────────────────────────┬───────────────┤
│ 任务列表      │ 工作区（cell 流）              │ 教练           │
│ t1 ✓ 读入数据 │ [t1] cell 1 代码 … 输出        │ 折叠卡片       │
│ t2 ● 区域聚合 │ [t2] cell 2 代码 … 断言结果    │ 提示阶梯       │
│ t3 ○ 窗口函数 │      + 新增草稿格              │ 对话           │
│ （锁定/复核） │ 每格：运行 / 重置 / 只读 diff   │ 应用 diff 按钮  │
└──────────────┴───────────────────────────────┴───────────────┘
```

- 三栏替代 `LessonDetail.vue` + `Playground.vue`；`AgentPanel.vue` 从悬浮窗改为右栏（保留移动端抽屉）。
- cell 组件统一：编辑器（保留现有行号 textarea）+ 输出区（stdout / 报错 / DataFrame 表格预览）
  + 断言结果条（每条断言的 ✓/✗ 与 expected/actual）。
- stale 视觉：下游格顶部一条灰条「上游已修改，需重跑」，任务列表出现"需复核"。
- 保留一个"自由实验区"入口（现有 Playground 简化版），但**不参与课程判定**。

## 10. 执行面（Runner）

新增 `execute_session` 能力（`learn_da_runner/runner/`）：

- 入参：`{program: [code...], stop_at: index, datasets: [{src, mount}], assertions: [...]}`；
- 实现在**单个子进程**内顺序执行各格：逐格捕获 stdout/stderr（用分隔标记切分），
  任一格异常即停止并标记该格 `error`，后续格 `skipped`；
- 数据集只读挂载：`local` provider 用临时目录 + `os.symlink`/复制（Windows 下复制），
  `docker` provider 用 bind mount `:ro`；
- 断言在最后一格执行完后、同进程内求值，返回逐条结果；
- 沿用现有硬限额（`RUNNER_TIMEOUT_SECONDS`、`RUNNER_MEMORY_LIMIT_MB`、`RUNNER_MAX_OUTPUT_BYTES`），
  新增"整次重放"总超时与"断言预算"；
- 安全：仍是 fail-closed，不联网、不写工作区外路径、不读 `expected/`（内存注入）。

## 11. 迁移与兼容

| 阶段 | 内容 | 可回退点 |
|---|---|---|
| M0 | 本设计稿 + 断言 DSL 单测骨架 + 数据集生成脚本（先造 `ecommerce` 一套） | 纯新增，零风险 |
| M1 | 后端表 + workspace API（内部用现有 execute 实现重放，断言先只支持 `expr_true`/`schema`） | 新端点未接前端 |
| M2 | Runner `execute_session` + 断言引擎 + 数据集挂载 + `frame_equal`/`sql_rows` | 旧 `/execute` 不动 |
| M3 | 前端三栏 + **03-polars-groupby 单课样板**（feature flag `WORKSPACE_V2`） | 单课灰度，可关 |
| M4 | 内容迁移到 13 课 + Coach 接入 + 旧页面下线 + 旧 validator 标 deprecated | 旧路由保留一个版本 |
| M5（可选） | 常驻 kernel 替换重放 | 接口不变 |

`exercise_attempts` 与新表并存；`test_security_settings` 等既有 409 项测试在 M1-M2 期间不删，
新增测试与旧测试并行（迁移完成后再按模块清理）。

### 11.1 M0 完成记录（2026-10-21）

已落地，全部为新增代码，不触碰旧链路（后端 445 项 / Runner 29 项 / 前端 103 项通过）：

- **数据集**：`learn_da/scripts/build_datasets.py`（`SEED=20251021`）生成
  `learn_da/content/datasets/ecommerce/{orders,customers,products}.csv` + `README.md` + `manifest.json`
  （orders 5000 行 / 365KB，合计约 409KB ≪ 5MB）。`--check` 校验仓库文件与生成器产物一致（sha256/字节/行数）。
  测试 `learn_da/tests/test_build_datasets.py`（9 项）。
- **断言 DSL**：`learn_da/app/practice/assertion_runtime.py`（求值实现，纯标准库，polars/duckdb 惰性导入）
  + `learn_da/app/practice/assertions.py`（校验 / 生成尾巴 / 解析结果）。
  测试 `learn_da/tests/unit/test_assertions_dsl.py`（27 项）。
- **实测**：真实 Runner 跑"读 CSV(5000 行) → group_by 聚合 → 4 条断言"，标准解 4/4 passed（577ms），
  把 `amount` 换成 `quantity` 后 a4 判失败并回传 actual（593ms）。
- **发现（影响 M2）**：`POST /api/v1/playground/execute` 与 Runner 的 `code` 字段都是 `max_length=5000`，
  内联运行时版本的程序约 10KB → 直接 422。所以 M2 的 `execute_session` 必须走"沙箱内预置
  `assertion_runtime.py` + 按路径加载的紧凑尾巴"（约 300 字节），或单独放开该接口的长度上限。

### 11.2 M1 + M2 完成记录（2026-10-22）

后端与 Runner 两侧都已落地，**旧 `/execute` 与旧 validator 完全不动**（后端 455 项 / Runner 39 项 / 前端 103 项通过）。

- **数据表**（迁移 `a7d1e4f2b9c3`，down_revision `c3f8a1b7e2d4`）：`lesson_sessions`、`session_cells`、
  `run_events`、`task_attempts`（`learn_da/app/workspace/models.py`）。会话按 `(visitor_id, lesson_slug)` 唯一，
  执行事件按 `(visitor_id, request_id)` 唯一做幂等。
- **API**（`learn_da/app/workspace/router.py`，模块名必须写进 `ENABLED_APP_MODULES`，否则 404）：
  `POST /api/v1/workspace/sessions`、`GET …/sessions/{id}`、`PUT …/cells/{cellId}`、
  `POST …/cells/{cellId}/run`、`POST …/tasks/{taskId}/submit`。
- **级联失效**：改第 k 格代码 → 第 k 格自身与之后所有格置 `stale`；已通过的任务若其所在格不再是 `ok`，
  视图状态回到 `todo`（需复核），不改历史 `TaskAttempt`。
- **幂等**：`RunEvent.payload` 存的是**完整响应体**（`RunResponse.model_dump(by_alias=True)`），
  同一 `requestId` 重放直接还原，含 `taskStatus`。
- **Runner**：`POST /v1/sessions`（`learn_da_runner/runner/main.py`）→ `provider.execute_session`；
  本地后端 `LocalSubprocessProvider.execute_session` 与 Docker 后端共用 `runner/session.py:prepare_workspace`
  写工作区（`driver.py` / `plan.json` / `assertion_runtime.py` / `data/…`），由 `runner/session_driver.py`
  在单进程内顺序重放，失败即停、后续格 `skipped`；只有前面的格子全部成功才求值断言，否则
  `assertionsSkipped=true` 并给 detail。路径校验拒绝绝对路径与 `..`（Windows 上 `Path('/etc/passwd').is_absolute()`
  为 False，额外判断前导 `/`、`\`）。
- **内容样板**：`learn_da/content/lessons/03-polars-groupby.md` frontmatter 新增 `workspace:`
  （数据集 `ecommerce/orders.csv`，3 格 = starter c1 + 任务 c2/c3，2 个任务共 5 条断言）。
  `content_loader` 把该块原样带进 lesson dict，结构由 `app/workspace/content.py` 校验。
- **实测（本机 local provider，真实 polars）**：
  - `python scripts/verify_workspace.py` → 「会话 1：3 个单元格，2 个任务」「c1 执行 passed（547ms）」
    「t1 全部 3 条断言 passed」「t2 全部 2 条断言 passed」「工作区自检通过」。
  - 起步代码提交 → `assertion_failed`，`t1-schema` 回传「缺少列 ['revenue', 'orders']（实际列：[…]）」，
    `t1-sorted` 因列不存在记 `error`（断言自身异常不算学员失败）。
  - 改 c2 → `staleFrom=c2`，`cells={c1:ok, c2:stale, c3:stale}`。
- **仍未做**：`frame_equal`/`sql_rows` 的真实 `refs` 来源（现为空字典，暂无课程使用）、
  沙箱内预置数据集与运行时（当前 Docker 路径靠请求体 base64 传数据集，课程加载时 ≤8MB 合计）。

### 11.3 M3 完成记录（2026-10-22，前端工作区 + 03 课样板接入）

三栏工作区在浏览器里真实跑通：`/lesson/polars-groupby` → vite 代理 → 后端 8000 → Runner 8080（local provider）
→ 真实 polars 读 `orders.csv`，t1/t2 全通过、改坏上游后断言失败并回显 `actual`。

- **前端资产**：`learn_da_vue/src/api/workspace.ts`（5 个端点封装）、`src/stores/workspace.ts`
  （Pinia：`snapshot/cells/tasks/runs/saveState/staleFrom`，编辑去抖 800ms 落库，`runCell`/`submitTask`
  先占位再 flush 防并发，`requestId` 用 `lib/uuid` 的 `randomId()`）、`src/views/LessonWorkspace.vue`
  （左任务列表 + 中单元格流 + 右任务详情，语义 token 全通过 `ui_lint`）。
- **路由灰度**：新增 `/lesson/:slug`（工作区），与旧 `/learn/:slug` 并存；课程是否进工作区由后端
  `LessonSummary.hasWorkspace`（`learn_da/app/learning/schemas.py`，来自 frontmatter 有无 `workspace:`）决定，
  `Learning.vue` 的 `goToLesson()` 据此分流。
- **单元格 UI**：运行 / 提交任务双按钮（提交是显式动作）、`StatusPill` 状态、`CodeOutput` 输出、
  断言列表（✓/✗/– + `actual` 截断回显）、`staleFrom` 警示条（仅当 stale 起点不是第一格才提示）、
  过期输出降透明并标注「结果已过期」（避免旧输出配新代码）、`Ctrl/⌘+Enter` 运行、`Shift+Enter` 换行。
- **实测（headless Edge + CDP，`.tmp_verify/ws_cdp.py`）**：c1 运行 `(5000, 11)` 578ms →
  c2 提交「任务 1/2」3 条断言全 ✓ → c3 提交「任务 2/2」2 条断言全 ✓ → 改坏 c2 重跑：`任务 0/2`、
  `t1-schema` 回「缺少列 ['orders']（实际列：['region','revenue']）」、c3 降为「待执行」+ 警示条。
  截图：`workspace-initial.png`、`workspace-t1-passed.png`、`workspace-all-passed.png`、`workspace-t1-failed.png`。
- **发现的真 bug（已修）**：开发环境 `learn_da_vue/.env.development` 原来把 `VITE_API_BASE_URL` 指向
  `http://127.0.0.1:8000/api/v1`，页面在 `localhost:5173` → 跨站请求，`SameSite=Lax` 的会话 cookie 不发送
  → 每个请求都是新访客（`lesson_sessions` 连续出现不同 `visitor_id`，随后 `run` 报「会话不存在」）。
  已改为 `/api/v1` 走 `vite.config.ts` 的代理（同源）。
- **测试**：前端新增 `src/stores/__tests__/workspace.spec.ts`（9 项：加载/错误/编辑去抖/无变化不打网络/
  提交先落库/并发守卫/失败复位/skipped 不算通过/重置），后端新增 `hasWorkspace` 断言。
  基线：后端 **456** / Runner **39** / 前端 **112**。
- **仍未做**：`/lab` 自由沙盒、`/report` 学习报告、其余 12 课迁移、教练侧栏接 `frame_equal` 建议动作
  （`propose → 确认` 未接）、旧 `/learn/:slug` 与 `/playground` 下线（留到 P4）。

### 11.4 M4 + P1/P3/P4 完成记录（2026-10-22，13 课迁移与页面重构）

用户验收 M3 后（"试用下来效果可以"）要求：其余 12 课迁工作区并「内容稍微整合一下」（加厚），其余按
§15.6 推进。本轮全部落地。

**内容（M4）**

- **13 门课全部迁到 `workspace:` 格式**，每课 3 个任务、3–11 条断言。数据课正文 260–330 行、纯 Python 课
  180–240 行（改前 `12-python-functions.md` 只有 66 行、`13-python-collections.md` 72 行）。
- 参考解按课拆文件：`learn_da/scripts/solutions/<slug>.py`（`SOLUTIONS: dict[cellId, code]`），由
  `learn_da/scripts/workspace_solutions.py` 聚合，避免多人并行改同一个 `SOLUTIONS` 字典。
- 自检 `learn_da/tests/test_workspace_content.py`（26 项 = 13 课 × 2）：进程内用
  `app/practice/assertion_runtime.py` 求值，逐课验证「起步代码在每个任务下必失败（L3）」+
  「参考解跑到该任务与整链重放都必全过（L4）」，外加任务数 ≥ 2、数据集 ≤ 5MB。
- **新增脏数据集** `content/datasets/ecommerce/orders_dirty.csv`（1230 行 = 1200 样本 + 30 整行重复）：
  `discount` 33 个空、`quantity` 23 个空、`amount` 混入 `N/A`（整列被读成 String）、`order_date` 42 行
  `2025/11/22` 斜杠格式、`region` 前后空格、`channel` 大写、重复 `order_id`。清洗课（05）用它，
  干净课继续用 `orders.csv`；生成器固定 seed，`--check` 校验 5 个文件字节一致。
- 写作规范独立成文：`learn_da/docs/workspace-content-spec.md`（`workspace:` 骨架、单元格约定、
  四型断言规则、正文 8 段结构、YAML 坑、数据集字段字典）。

**后端（进度与报告）**

- `learn_da/app/workspace/progress.py`：`lesson_progress()` / `learning_report()`，只读 `task_attempts`
  与内容索引，不依赖 Runner。返回课程级 `status`（`not_started|in_progress|completed`）、`currentTaskId`、
  track 汇总、`tasksFirstTry`、`activeDays`/`streakDays`、`errorPatterns`（按 `(lesson, task, assertionId)`
  聚合，带 `lastActual`）、`recent`。
- 新端点 `GET /api/v1/workspace/progress`、`GET /api/v1/workspace/report`；
  测试 `learn_da/tests/unit/test_workspace_progress.py`（5 项）。

**前端（P1/P3/P4）**

- `/learn` 换成 `CourseMap.vue`：三个汇总卡 + 「继续上次」+ 按 track 分组的进度与「开始/继续/复习」，
  1 击直达任务（`?task=`）；首页顶部加 `ContinueStrip.vue`。
- `/report` → `Report.vue`：5 张指标卡、能力分布、常见卡点（可点回课程）、最近提交表格；一次通过率口径
  写在小字里（分母 = 已通过任务 + 卡点去重后的失败任务数）。
- `/lab` → `Lab.vue`：自由沙盒（行号列、`Ctrl/⌘+Enter`、`CodeOutput`、数据集参考侧栏）；语言下拉只启用
  Python（后端构造 Runner 请求时不传 `language`，沙箱 schema 是 `Literal["python"]`），SQL 置灰。
- Navbar 导航收敛为 **今日 / 课程 / 报告 / 实验室**，raw palette 清零。
- **P4 下线旧页**：路由从 9 条降到 6 条（`/`、`/learn`、`/lesson/:slug`、`/report`、`/lab`、404）。
  删除 `Learning.vue`、`LessonDetail.vue`、`Playground.vue`、`Dashboard.vue`、
  `composables/useLessonSession.ts`、`composables/usePlaygroundSession.ts` 及其 2 个 spec；
  `App.vue` 去掉深色全屏分支与 `KeepAlive` 白名单。
  `ui_lint` 基线从 61 文件 / 558 处收紧到 **63 文件 / 225 处**。
- **暂时成死代码（待接回）**：`components/agent/AgentPanel.vue` + `composables/useAgentConversation.ts` +
  `stores/playground.ts`（AI 聊天面板原本只挂在 Playground 上）、`components/recommendation/RecommendationPanel.vue`。
  Agent 后端与 `/api/v1/agent/chat` 未动，聊天面板将随 §8.2 的分档介入一起接回。

**实测**

- 后端 `pytest -q` → **488 passed**；Runner **39 passed**；前端 **113 passed（17 文件）**；
  `vue-tsc --build`、`npm run lint:ui`、`content_lint.py`、`build_datasets.py --check` 全通过。
- `npm run build` 在本机被 esbuild 临时文件权限拦住（`Access is denied` 于 `%TEMP%\esbuild-<hash>`），
  已排除 tailwind/minify/target/manualChunks/TEMP 位置等因素，判定为 Windows 沙箱/杀毒拦截，
  换机器或服务器构建验证。

**仍未做**

- AI 教练面板（工作区内分档介入 + 动作白名单）未接回；课程断言实际只用 `schema` + `expr_true`
  （`frame_equal`/`sql_rows` 需要 `refs`，暂未接入内容管线）。
- `/lab` 的 SQL 支持、移动端适配、灰度开关 `WORKSPACE_V2`（旧页已删，不再需要）。

## 12. 测试策略

- **断言 DSL**：每种类型的通过/失败/异常/超时；`expr_true` 的命名空间白名单（禁 import/写文件）。
- **重放语义**：改上游 → 下游 stale；跳格执行被拒；幂等（同 requestId 只写一条 RunEvent）。
- **lint**：构造 8 类坏课程（L1-L8 各一），必须 fail-closed 并给文件名。
- **数据集可复现**：同种子两次生成字节一致，hash 稳定。
- **端到端**：一课的完整链路（建会话 → 跑 starter 失败 → 应用提示 → 通过 → 提交 → 下一任务解锁），
  用 `scripts/verify_workspace.py` 跑真实 Runner（沿用 `verify_exercises.py` 的做法）。
- **回归**：现有后端 409 / Runner 29 / 前端 71 必须持续通过；旧 `/execute` 行为不变。

## 13. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 重放延迟（前缀越长越慢） | 体感卡顿 | 数据集 ≤5000 行、前缀目标 <3s；前端乐观渲染"正在重放 1..N 格" |
| 无账号 + 会话丢失 | 换浏览器进度丢 | 服务端会话为权威；localStorage 缓存草稿；预留"会话 id 恢复链接" |
| 答案弱可见性 | 学习者可偷看 ref | 内存注入不落盘；记录 attempt；难度上不为难 |
| 严格顺序带来的挫败 | 改一格全下游重做 | stale 只要求重跑、不丢代码；任务"需复核"而非清零 |
| 内容工作量（13 课 × 3-6 task） | 周期长 | 先 1 课样板；再按 track 分批（polars 6 课 → duckdb 4 课 → python 3 课） |
| 内存（服务器 1.9G 可用） | 并发差 | 重放式无常驻进程，单次执行受 `RUNNER_MEMORY_LIMIT_MB` 限制；并发限流 |

## 14. 已确认项（2026-10-21，用户全部按建议采纳）

1. **草稿格**：允许（`kind=scratch`，不参与断言，参与重放）。
2. **自由实验区**：保留简化版 Playground（`/lab`），只读同一套数据集，不参与课程判定。
3. **跳任务**：允许，记 `skipped`，不计入完成率与能力雷达。
4. **数据集脏度**：t1 干净，后续任务逐步引入缺失值/重复/类型坑。
5. **灰度期**：保留旧 `/playground` 与旧课程页，`WORKSPACE_V2` 开关切换。
6. **样板课**：先做 `03-polars-groupby`（3 个任务：读入校验 → 区域聚合 → 窗口占比）。

## 15. 页面重构（2026-10-21 定稿）

### 15.1 痛点与量化证据

用户选定的痛点页面（多选，4/5）：Playground、课程详情页、学习看板、课程列表（**首页未选 → 不改结构**）。
痛点类型：信息架构、交互细节、视觉一致性（移动端与性能未列，本轮不做专项）。

审计结果（`src/**` 共 45 个文件，全部实测）：

| 维度 | 现状 | 结论 |
|---|---|---|
| 配色 token | `main.css` `@theme` 已定义 `primary-*` / `success-*` / `warning-*` / `danger-*`，但引用 **0** 次；实际用 `blue-*` 201、`emerald-*` 100、`slate-*` 431、`red-*` 22、`orange-*` 15、`indigo-*` 5 | token 是死代码，语义色未落地 |
| 圆角 | `rounded-full` 53 / `lg` 49 / `xl` 31 / `2xl` 28 / `md` 2 | 5 种并存，卡片无统一档位 |
| 阴影 | `md` 9 / `sm` 9 / `lg` 3 / `xl` 3 / `2xl` 1 | 5 种并存 |
| 组件复用 | `src/components` 仅 4 个文件；全站手写 `<button>` **92** 个、原生 `<input>` 2、`<textarea>` 3 | 无基础组件层 |
| 反馈机制 | `toast/notification` **0** 处、`confirm()` 0 处 | 无瞬时反馈、无危险操作确认层 |
| 三态 | `Playground.vue`(1525 行)、`LessonDetail.vue`(1188 行) 的 `skeleton` 均为 **0**；`Dashboard.vue` 有 loading（4）/ error（9）/ empty（6） | 最常用两页无加载骨架 |
| 键盘 | 全站 `keydown` 事件 **6** 处 | 无快捷操作体系 |

### 15.2 信息架构（最终路由）

| 路由 | 页面 | 单一职责 | 出口（"下一步"去哪） |
|---|---|---|---|
| `/` | 今日（Home，P5 已重构） | 回答「我现在该做什么」：继续上次 + 卡点 + 接下来 | 主卡「继续」→ 上次未完成任务；卡点卡「回去看看」→ 该任务；两条入口 → `/lab`、`/report` |
| `/learn` | 课程地图 | 按 track 纵览，看清每课任务级进度 | 点课 → `/lesson/:slug`；「继续」→ 上次任务 |
| `/lesson/:slug` | 工作区（三栏） | 读懂任务 → 写 cell → 提交验证 | 任务完成 → 就地展开下一任务；课程完成 → `/learn` |
| `/lab` | 自由沙盒 | 不判定的试手区（数据集浏览 + 快跑） | 无强制出口 |
| `/report` | 学习报告 | 用 `task_attempts` 真实计算能力与错误模式 | 薄弱维度 → 对应课程 |
| `/:pathMatch(.*)*` | 404 | — | 回 `/learn` |

主导航 4 项：今日(/) · 课程(/learn) · 报告(/report) · 实验室(/lab)。
`/lesson/:slug` 与 `/lab` 不占导航项（工作区态，用面包屑返回）。
会话深链：`/lesson/x?s=<sessionId>&task=<taskId>`，刷新与分享都不丢位置。

三条主流程的点击成本：

- **新访客**：`/` → 选 track（1 击）→ `/learn` → 第一课（1 击）→ 首任务已在工作区（0 击）。
- **回访**：`/` 顶部「继续」→ 上次会话最后未完成任务（**1 击**，现状需 3 击且常要自己回忆学到哪）。
- **卡住**：失败卡片内联显示断言 `actual` → 点「要提示」（原地逐级）→ 仍不懂 → 右栏 AI 抽屉自动带证据。

### 15.3 交互细节

- **动作分级**：主 = 提交任务（每页唯一实心主按钮）；次 = 运行 cell；三级 = 要提示 / 问 AI（描边或纯文字）。
- **快捷键**：`Ctrl/Cmd+Enter` 运行当前 cell；`Shift+Enter` 运行并下移；在任务卡上 `Ctrl/Cmd+Enter` 提交；`?` 打开快捷键浮层。
- **三态统一**：所有网络连接页面必须有 skeleton / empty / error+重试三态，由新增 `src/composables/useAsyncState.ts` 承载（`state: loading|ready|empty|error`、`retry()`），禁止页面内各写一套 `isLoading`（现状 56 处）。
- **反馈层级**：状态变化用 inline（按钮内 loading、任务卡状态药丸）；瞬时事件用新增 `useToast.ts` + `<ToastHost>`（"已复制/已保存/云端保存失败，已存本地"）；**不用 `window.confirm`**，危险操作走 `<ConfirmDialog>`。
- **防丢**：cell 内容写 `localStorage`（key `workspace:{sessionId}:{cellId}`）+ 服务端 PUT 去抖 800ms；PUT 失败进重试队列并在状态栏提示，不静默丢稿。
- **可发现性**：空状态必须给出下一步动作（`<EmptyState>` 强制 `cta` 属性），不允许只画一个图标加一句话。

### 15.4 视觉统一（token 落地 + 组件收敛）

语义 token（写入 `src/assets/styles/main.css` 的 `@theme`，替换现有 primary/success/warning/danger 命名）：

- 品牌：`--color-brand-50…700`（沿用 #2563eb 系）
- 状态：`--color-ok-*`（#16a34a 系）、`--color-warn-*`、`--color-err-*`
- 中性：`--color-ink-900/700/500/300`（文本层级）、`--color-surface-page/card/raised`（背景层级）、`--color-line`
- 形状：`--radius-card` 0.75rem、`--radius-control` 0.5rem、`--radius-pill` 999px；`--shadow-card`、`--shadow-pop`

约束（新增 `learn_da_vue/scripts/ui_lint.mjs`，挂进 `npm run lint:ui` 与提交前检查）：

- 禁止在 `src/**` 新增 `blue-* / emerald-* / red-* / orange-* / indigo-* / green-*`（raw palette 只允许在 `main.css` token 定义里出现）。
- 圆角只允许 `rounded-card / rounded-control / rounded-full`；阴影只允许 `shadow-card / shadow-pop`。
- 报错必须给出 `文件:行`，便于逐个收敛。

组件清单（`src/components/ui/`，替换点写明）：

| 组件 | 替换 |
|---|---|
| `<AppButton variant="primary\|secondary\|ghost" size="sm\|md" loading>` | 92 个手写 button |
| `<AppCard title padded>` | 各页卡片外壳 |
| `<AppField>` / `<AppInput>` | 2 个原生 input |
| `<StatusPill state="todo\|in_progress\|needs_review\|passed\|failed\|skipped">` | 四散的状态标签 |
| `<CodeOutput stdout stderr durationMs status>` | Playground 输出面板 + 工作区输出 |
| `<EmptyState title hint cta>` | 各页空白态 |
| `<ConfirmDialog>` / `<ToastHost>` / `<ShortcutHelp>` | 新增 |

排版四档：page 24/700、section 18/600、card 15/600、label 12/500；正文 15/1.7；代码 13 等宽。
**本轮不做暗色主题，不做移动端专项**（预留工作区单栏切换，不承诺优化）。

### 15.5 验收标准

1. 导航：任一课程任务 ≤2 次点击可达；回访「继续」= 1 次点击。
2. 视觉：`npm run lint:ui` 0 违规；`src/**` 中 raw palette 引用为 0（token 定义除外）。
3. 交互：`/`、`/learn`、`/lesson/:slug`、`/report`、`/lab` 五页均具备 skeleton/empty/error 三态；工作区刷新后 cell 内容与最近运行结果不丢。
4. 组件：手写 `<button>` 归零（工作区 cell 内微型图标钮除外，需在 lint 白名单注明原因）。
5. 测试：新增 vitest 用例覆盖 `useAsyncState`、`useToast`、`StatusPill`、`AppButton loading`；`npm test` 与 `vue-tsc --build` 全绿。

### 15.6 实施顺序（独立可合，旧页保留到 P4）

| 阶段 | 内容 | 依赖 |
|---|---|---|
| **P0** | token 落地 + `ui_lint.mjs` + 基础组件（`components/ui/*`，纯新增，不改页面行为） | 无 |
| P1 | `/learn` 课程地图（任务级进度） | M1（task_attempts） |
| P2 | `/lesson/:slug` 工作区外壳 + 三栏 + 快捷键 + 防丢 | M2/M3 |
| P3 | `/report`（真实能力计算） | M1 + 至少 3 课有 task 数据 |
| P4 | `/lab` + 下线旧 `/playground` 与旧课程页 | P0-P3 |

P0 完全不依赖后端改造，可以先做且风险最低。

#### P0 完成记录（2026-10-21）

- **token**：`learn_da_vue/src/assets/styles/main.css` 的 `@theme` 已换成 `brand/ok/warn/err/ink/surface/line`，并定义 `--radius-card|control|pill`、`--shadow-card|pop`；旧的 `primary/success/warning/danger` 四个 token 删除（审计时引用数为 0）。
- **规范检查**：`learn_da_vue/scripts/ui_lint.mjs` + 基线 `scripts/ui_lint.baseline.json`（存量 61 文件 / 558 处，只允许减少）；`src/components/ui/**` 零容忍。脚本命令 `npm run lint:ui`、`npm run lint:ui:baseline`、`npm run check`（type-check + lint:ui）。
- **基础组件**：`src/components/ui/` 下 `AppButton`/`AppCard`/`AppInput`/`StatusPill`/`CodeOutput`/`EmptyState`/`ConfirmDialog`/`ToastHost` + `status.ts` + `index.ts`（barrel）；配套 `useAsyncState`（三态 + 竞态丢弃）、`useToast`（模块级队列）两个 composable，`App.vue` 挂 `<ToastHost />`。
- **测试**：新增 5 个 spec（`useAsyncState`/`useToast`/`AppButton`/`StatusPill`/`ConfirmDialog`），前端 71 → **103 passed**；`vitest.config.ts` 补 `vue()` 插件（此前导入 `.vue` 会报缺少 plugin-vue）。
- **未做（留到后续阶段）**：`ShortcutHelp`（`?` 快捷键说明）随 P2 快捷键一起做；页面本身未改（旧 `Playground`/`LessonDetail` 仍在，按 §15.6 保留到 P4）。

#### P1/P3/P4 完成记录（2026-10-22）

- **P1 `/learn`**：`src/views/CourseMap.vue`（三个汇总卡 + 「继续上次」+ 按 track 分组进度 + 开始/继续/复习 CTA，直达 `?task=`）；首页顶部 `components/home/ContinueStrip.vue`（P5 已并入首页主卡，组件删除）；数据来自 `GET /api/v1/workspace/progress`。
- **P2 工作区外壳**：`/lesson/:slug` 三栏（已在 §11.3 记录）；本轮补深链 `?task=<taskId>`（`router.replace` 同步，`onMounted` 命中 query 则聚焦，否则落第一个未通过任务）。
- **P3 `/report`**：`src/views/Report.vue`（5 张指标卡、能力分布、常见卡点可点回课程、最近提交表格），数据来自 `GET /api/v1/workspace/report`。
- **P4 `/lab` + 下线旧页**：`src/views/Lab.vue` 自由沙盒（行号列、`Ctrl/⌘+Enter`、`CodeOutput`、数据集参考侧栏，SQL 置灰）；删除 `Learning.vue`/`LessonDetail.vue`/`Playground.vue`/`Dashboard.vue` 与 `useLessonSession`/`usePlaygroundSession` + 2 个 spec；路由 9 → 6 条；`App.vue` 去掉深色全屏与 `KeepAlive`。
- **导航**：Navbar 4 项（今日 / 课程 / 报告 / 实验室），raw palette 清零。
- **基线**：后端 488 / Runner 39 / 前端 113；`ui_lint` 基线 63 文件 / 225 处（P0 时 61 / 558）。
- **仍缺**：`ShortcutHelp`（`?` 说明面板）、AI 教练面板接回、`/lab` 的 SQL 支持。（`npm run build` 在本机被 esbuild 临时文件权限拦住，需在普通终端或服务器验证；2026-10-22 用户已在普通终端验证通过。）

#### P5 首页重构为「今日」（2026-10-22，用户追加要求）

改造前 `Home.vue`（462 行）是营销页：深色渐变 hero + 平台级统计（今日活跃 / 代码运行次数）+ 三张路径卡（与 `/learn` 重复）+ 「为什么选择路径化学习」+ 底部大 CTA，raw palette 45 处 / 圆角 10 处 / 阴影 3 处，且首页对「回访者下一步做什么」没有答案。

改造后单一职责 = 「我现在该做什么」，数据只取 `GET /workspace/report`（`task_attempts` 真实聚合）：

1. **主卡**：最近动过的 in-progress 课（没有记录则第一门未完成课）→ 标题 + `passedTasks/totalTasks` + 估时 + 进度条 + 主按钮「继续/开始学习」，跳转带 `?task=<currentTaskId>`。
2. **指标带**：已通过任务、完成课程、一次通过率（`tasksFirstTry / tasksPassed`）、连续学习天数。
3. **卡点卡**：`errorPatterns[0]` → 「课程 › 任务」+ 失败次数 + `lastActual`（截断后的实际值）+ 「回去看看」直达该任务。
4. **接下来**：最多两门未完成课（排除主卡那门），各带一个 CTA。
5. **学习路径**：4 条 track 的进度条（`ratio` 是 0–1 小数，渲染时 ×100）。
6. **入口**：`/lab`、`/report` 两张卡。

删除项：深色 hero 与入场动画、`fetchHomeStats` / `fetchCategoryStats` 调用、`learningTracks` legacy 兜底文案、`learnerState` 依赖、`components/home/ContinueStrip.vue`（职责并入主卡）。文案里不再出现平台级「今日活跃」，`daysSinceActive ≥ 3` 只在概览行点一句「已经 N 天没练了」。

测试：新增 `src/views/__tests__/Home.spec.ts`（10 项：主卡选择与深链、无记录降级、指标与一次通过率、卡点跳转、接下来最多两门、路径进度用后端 `ratio`、三天未练提示、全部完成后主卡退回复习、失败重试、空态 CTA）。前端 113 → **123 passed（18 文件）**；`vue-tsc --build` 通过；`ui_lint` 基线因 `Home.vue` 归零从 63 文件 / 225 处收紧到 **63 文件 / 167 处**。
## 16. AI 教练 E0：证据链接改版（2026-10-23）

改造前的断点：`app/agent/evidence.py` 只读冻结的 `exercise_attempts`，全项目对 `workspace` / `TaskAttempt` 的引用为 0 —— 在工作区里问 AI，永远返回 `no_evidence`；FC 工具还停留在「练习 + stdout」语境；模型不可用时返回的是按意图预置的话术，像是真的回答过。

### 16.1 用户决定（2026-10-23）

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 角色 | **只解释，不改代码** | 不做 `replace_cell` 等动作白名单，先把「说得对」做扎实 |
| 第一里程碑 | **先接证据**（evidence 改读 `TaskAttempt` + 断言 `actual`，FC 工具改 task 语境） | 证据不对，介入形态再花哨也没用 |
| 降级 | **模型不可用就明说不可用** | 不做规则话术兜底，避免"看起来答了其实没答" |

### 16.2 数据与仓储

- `task_attempts` 新增 `verdict`（Runner 原始结论：`passed` / `assertion_failed` / `execution_failed`），迁移 `f4b8d1c6a2e7_task_attempt_verdict` 并回填历史行（`status=passed → passed`、`skipped → execution_failed`、其余 `assertion_failed`）。
- 新 `app/workspace/repository.py`：`spec_for(lesson_slug)` 与只读仓储 `WorkspaceReadRepository`（`get_attempt` / `latest_attempt` / `recent_attempts` / `passed_task_ids` / `lesson_task_stats` / `progress`）。

### 16.3 证据

`AgentEvidenceResolver` 现在**优先 workspace**：有 workspace spec 的课走 `_resolve_workspace`，否则回落到旧 `_resolve_exercise`（历史数据只读）。

- 五态由 `derive_workspace_state(verdict, status)` 推导：`passed`→`passed_unconfirmed`；`execution_failed`（含 `status=skipped`）→`execution_failed`；`assertion_failed`→`verification_failed`；`status=skipped`→`unverifiable`；无提交→`no_evidence`。
- 证据里带**任务语境**：`task_id/task_title/task_objective`、`tasks_passed/tasks_total`、`current_task_id`、`lesson_completed`（由通过任务数推导）。
- 断言结果最多 8 条、**失败在前**，每条带 `detail` 与 `actual`（截断 300 字符）——这是"错在哪"的唯一来源，不用客户端自报。
- `next_action`：`passed_unconfirmed` 且课程未完成时返回 **`next_task`**（取代 `confirm_lesson`）。
- 越权防护：`attemptId` 必须属于该访客且属于该课，否则忽略并回落到"该课最近一次提交"。

### 16.4 编辑器代码与证据冲突（实测发现的坑）

真实链路复验时出现过自相矛盾的回答：任务已通过，模型却说「你的代码还缺 orders 列」——因为 `context.currentCode` 是编辑器里的旧代码。

修法：证据新增 `code_matches_editor`（比较 `attempt.code` 与 `context.currentCode`，只比较不入库），不一致时证据块追加「编辑器里的代码不是最近一次提交的代码……不要据此说『你还缺 X』」；上下文块也把代码标注为「可能已改动但尚未提交」。

### 16.5 工具与降级

- FC 工具：`get_exercise_summary` → **`get_task_summary`**（`lesson_slug?` / `task_id?`），返回最近提交的任务、判定结论与失败断言（最多 5 条、单条 240 字符）；`get_learner_progress` 追加工作区任务进度。
- 模型不可用：`FALLBACK_UNAVAILABLE_CONTENT` —— 明确说「AI 助手暂时不可用（模型调用失败），这次我不会编造回答」，并说明 `teachingFeedback` 仍是服务端权威结果。

### 16.6 实测（真实 Runner + dashscope `qwen3.7-flash`）

| 场景 | 结果 |
| --- | --- |
| 提交错误代码（按 `quantity` 求和当 revenue） | `verdict=assertion_failed`；`t1-schema` 回「缺少列 ['orders']（实际列：['region','revenue']）」，`t1-sorted` 回「…为假（实际值：False）」 |
| 失败后提问 | `usedFallback=False`、`state=verification_failed`、`nextAction=retry_exercise`、`attemptId` 正确；回答准确指出缺 `orders` 列与未排序 |
| 提交参考解后提问 | `state=passed_unconfirmed`、`nextAction=next_task`；回答「t1 已通过」并提示编辑器代码不是提交版本 |

脚本坑：同一 `requestId` 重复提交会被 `run_events` 幂等缓存返回旧结果，冒烟脚本必须每次用新 requestId。

### 16.7 未做（留给 E1/E2）

- 介入形态（失败卡片、阶梯提示 `POST /workspace/tasks/{id}/hint`、`hint_usages` 表）—— §8.2 的三档仍只有 chat。
- 动作白名单（§8.3）—— 用户本轮明确不做。
- 前端入口：`AgentPanel.vue` 仍是死代码，工作区里还没有入口（前端类型已同步 `nextTask` 与 `currentTask`）。

测试：后端 490 → **510 passed**（新增 `tests/unit/test_agent_workspace_evidence.py` 20 项）。

## 17. AI 教练 E1：工作区接上对话入口（2026-10-24）

### 17.1 用户决定（2026-10-24）

| 问题 | 决定 | 理由 |
|---|---|---|
| 后端能否流式 | **E1 先做诚实的非流式** | `/agent/chat` 是 FC 多轮 + 一次性返回，没有 SSE；前端原来「先拿到整段再当 token 吐出去」是打字机假象。E1 改成「正在思考…」→ 整段落地；真 SSE 要等 FC 增量 tool_calls，留 E2 |
| 是否现在做 ladder 阶梯提示 | **不做，留 E2** | 需要新建 `hint_usages` 表、`POST /workspace/tasks/{id}/hint` 端点、越层校验，是独立一块 |
| Agent 架构 | 沿用 **确定性策略层 + 单一 LLM 表达层** | 判定（五态、失败断言、提示层级、next action）全在 Python；模型只负责讲人话 + 答开放问题。不引入 planner/executor/critic，也不做 RAG-first |

### 17.2 后端三处修补

1. **`hint_level` 进 prompt（真实缺陷）**：原来服务端算出的层级只回前端展示，模型完全不知道当前该给第几层提示。新增 `prompts.build_hint_directive(hint_level)`（L1 只指方向 / L2 可说 API 名不给完整语句 / L3 可给一行关键写法），`service._with_hint_directive` 把它作为一条 system 消息**插在提问之前**（保持 system prompt 仍在首位）；`build_evidence_block` 也接受 `hint_level`。
2. **`AgentContext` 扩展**：新增 `sessionId` / `cellId` / `recentRuns`（`AgentRecentRun`：`cellId` / `status` / `errorType` / `stderrFirstLine` / `assertionsFailed`，最多 3 条、stderr 截 400、失败断言截 8 条）。`build_context_block` 注入「工作区会话 / 当前聚焦的单元格 / 最近的单元格执行」，并明确标注**客户端自报、仅供定位、判定以服务端证据为准**。
3. **FC 工具不新增**：`get_task_summary` / `get_learner_progress` / `search_knowledge` / `get_recommendation` 已覆盖；不引入任何写工具（用户已定「只解释不改代码」）。

### 17.3 前端

- 新建 `learn_da_vue/src/components/workspace/WorkspaceCoach.vue`（+ `index.ts` barrel），工作区右栏三段：
  - **ambient 证据卡**：直接渲染 `store.runs[cell].assertions` 里未通过的那些（`actual || detail`），**0 请求 0 token**，因此永远与判定一致；底部一个「这条断言为什么不通过」按钮，把失败断言标题拼进提问。
  - **chat**：`useAgentConversation` + 空态三条具体建议（不给空白输入框）、`正在思考…` 占位、消息尾部显示「提示层级 L{n} · 状态」、错误行内显示不弹 toast。
  - **聚焦格变化时清空对话**（旧对话会误导模型）。
- `LessonWorkspace.vue`：占位卡片换成 `<WorkspaceCoach :context="coachContext" :assertions="coachAssertions" :has-submission="coachHasSubmission">`；`coachContext` 组装 `currentLesson/lessonTitle/lessonCategory/currentTask/sessionId/cellId/currentCode/recentRuns`（`recentRuns` 取 `runs` 末 3 条，含 `stderrFirstLine` 与 `assertionsFailed`）。
- **去掉伪流式**：`api/agent.ts` 的 `streamChatMessage` 改名 `sendChatMessage`（删除 `onToken`），`useAgentConversation` 同步；注释写明「后端一次性返回，E2 再引入 onToken」。

### 17.4 死代码清理（本轮）

删除 `src/components/agent/AgentPanel.vue`（870 行）、`src/components/recommendation/RecommendationPanel.vue`、`src/components/playground/TutorialSidebar.vue`、`src/lib/recommendation.ts`、`src/stores/playground.ts` + 两个重复的 `playground.spec.ts`、空目录 `components/common`、`components/editor`；`localState.ts` 删掉 `playgroundDrafts`/`isAgentOpen`/`openAgent`/`closeAgent`/`toggleAgent` 与对应类型 `PlaygroundDraft`/`PlaygroundDrafts`。`scripts/ui_lint.baseline.json` 从 **63 文件 / 167 处**收紧到 **59 文件 / 14 处**。

### 17.5 测试与实测

- 新增 `learn_da/tests/unit/test_agent_coach_context.py` **19 项**（层级措辞、钳制、插入位置、recentRuns 上限与 camelCase、stderr 截断、层级真的进到模型 prompt 的 6 组 helps→level 参数化）。
- 新增 `learn_da_vue/src/components/workspace/__tests__/WorkspaceCoach.spec.ts` **11 项**（ambient 只显示未通过项、error/skipped 也算未通过、按失败断言提问、上下文随请求发送、空态建议、思考占位、层级展示、错误行内、Ctrl+Enter、换格清空）。
- 后端 **510 passed**；前端 **117 passed（17 文件）**；`vue-tsc --build` 通过；`npm run lint:ui` 通过。
- 本轮**未做真实浏览器验证**（用户 m02550 要求跳过浏览器验证，改为交付手动验证清单）。

### 17.6 未做（留给 E2）

- ladder 阶梯提示（`hint_usages` 表 + `POST /workspace/tasks/{id}/hint` + 越层校验）。
- 真流式（SSE / FC 增量）。
- 动作白名单（§8.3）—— 用户明确不做。
