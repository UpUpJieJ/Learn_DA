# Phase 2: 可验证练习闭环设计

**日期：** 2026-07-29
**状态：** 待实施
**依据：** `docs/iteration-roadmap-2026-07-14.md` 第 6 节

## 目标与范围

把“阅读课程后手动完成”升级为可审计的闭环：学习者进入练习、提交代码、分别获得执行与验证结果、恢复未完成工作，并在验证通过后自行确认课程完成。

首批仅覆盖 `python-functions`、`polars-basics`、`duckdb-sql-foundations`。不引入 LLM 判题、任意 Python 判题脚本、自动完成课程或多题型系统。

## 现状与决策

- `practice_objective` 与 `completion_criteria` 是展示文案，不承担机器判定；首批课程迁移为正式 `exercise` 定义，旧字段仅兼容读取。
- `requestId` 标识一次执行请求，不能充当领域 Attempt；服务端为每次练习提交创建持久化 `attemptId`。
- `LearnerLessonProgress` 的计数继续作为汇总投影；`ExerciseAttempt` 是可追溯事实来源。
- DuckDB 首批练习使用 Python DuckDB API，不依赖当前未实现的独立 SQL 执行模式。

## 内容契约

课程 frontmatter 新增可选 `exercise`；没有它的课程继续作为纯内容课程，有它时必须完整合法。

```yaml
exercise:
  id: python-functions-add-bonus-v1
  title: 为成绩添加 bonus
  language: python
  starter_code: |
    def add_bonus(score):
        # TODO
        pass
    print(add_bonus(95))
  objective: 定义接收 score 的函数，返回加 5 后的值。
  hints: [先把 score 放在函数参数中, 用 return 返回 score + 5]
  validator:
    type: stdout_exact
    expected: "100"
```

首批判定器为声明式、确定性的 `stdout_exact`、`stdout_contains`、`dataframe_rows`，分别基于规范化 stdout、字符串集合和 Runner 返回的数据帧列/行。判定规则只由仓库中受信任 YAML 表达：禁止内容表达式、动态脚本、动态 import 和 LLM。

## Attempt 与 API 契约

新增 `exercise_attempts`：`visitor_id`、`lesson_slug`、`exercise_id`、`request_id`、`execution_id`、`source`、`language`、`code`、`execution_status`、`verification_status`、`failure_reason`、受限 stdout/stderr、`duration_ms` 与时间。

- `(visitor_id, request_id)` 唯一；重放返回同一 Attempt，不新增计数或事件。
- `attemptId` 是服务端主键，`executionId` 来自 Runner；都在响应中返回。
- `verificationStatus` 为 `not_run`、`passed`、`failed`、`unverifiable`。Runner 不可用、超时、拒绝和代码错误不进入判定器。
- `POST /playground/execute` 增加成对可选的 `lessonSlug/exerciseId`；缺省保持普通 Playground 行为，提供时必须匹配课程练习。
- 响应增加 `attemptId` 和 `verification`，现有 `status` 始终只表达执行状态。

执行顺序：校验练习定义 -> 调 Runner -> 确定性判定 -> 写 Attempt 和 `code_run` -> 更新 Learner State -> 提交事务 -> 返回。Runner 业务失败也必须保存为 Attempt。

## 恢复、完成与 Agent

`GET /playground/exercises/{exercise_id}/resume` 优先返回最近未通过 Attempt 的代码，否则返回 starter code；localStorage 草稿仅作离线兜底。验证通过后只显示“查看证据并完成课程”，用户点击后仍通过 `/analytics/track` 写 `lesson_complete`，不得自动完成。Agent 和推荐只读取 Attempt 摘要（exercise、执行/验证状态、错误类型、时间），不读取完整代码。

## 验收

1. 三节样板课程可从课程页进入练习、执行并获得确定性验证结果。
2. 执行成功但判定失败、执行失败、Runner 不可用、验证通过在 API、数据库和 UI 中可区分。
3. 相同 request ID 重放只产生一条 Attempt 和一次学习投影。
4. 刷新后可恢复最近未通过代码；验证通过后不会自动完成课程。
5. 至少 80% 的首批判定由确定性判定器完成，且没有 LLM 参与。
