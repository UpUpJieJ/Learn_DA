# Phase 2: 可验证练习闭环实施计划

**状态：** 待实施
**前置：** 阶段 0、阶段 1 与 Agent 功能收口已完成；Task 9 按当前决策不实施。
**设计：** `docs/superpowers/specs/2026-07-29-phase2-verifiable-practice-design.md`

首批仅交付 `python-functions`、`polars-basics`、`duckdb-sql-foundations` 三节 tracer 课程。每项先写失败测试；数据库写路径必须覆盖 visitor 隔离、请求重放和事务边界。

## Task 1: 练习内容 schema 与 lint

修改 `app/core/content_loader.py`、`app/learning/schemas.py`、`app/learning/repository.py` 和三节课程。定义 Pydantic `ExerciseDefinition`、`ExerciseValidator` 与受限 validator 枚举；对有 `exercise` 的 frontmatter fail closed；增加 content lint 和测试。

**验收：** 三个 exercise 可解析；缺字段、未知 validator、重复 ID 和语言不匹配都带文件名失败；普通课程仍可加载。

## Task 2: Attempt 数据模型、迁移与 repository

新增 `app/practice/`、`ExerciseAttempt`、model registry 和 Alembic migration。以 `(visitor_id, request_id)` 唯一约束保证重放幂等；限制代码和输出长度；提供按 visitor + exercise 查询最近 Attempt 的读取方法。

**验收：** 重放不新增 Attempt；跨 visitor 不可读取；迁移可升级回滚。

## Task 3: 受限确定性验证器

新增 `app/practice/validator.py` 和单测。实现 `stdout_exact`、`stdout_contains`、`dataframe_rows` 纯函数验证器，固定输出规范化和 failure reason code，禁止 `eval`、动态 import、内容可执行脚本和 LLM。

**验收：** 结果只由执行输出和练习定义决定；执行错误不会误标成练习失败。

## Task 4: Playground 练习执行编排

扩展 `app/playground` 的 schema、service 和 router。execute request 增加成对的 `lessonSlug/exerciseId`；普通执行不变，练习执行创建/重放 Attempt、调用 Runner、再判定；响应增加 `attemptId` 与 `verification`。同一事务写 Attempt、`code_run` 和 Learner State。

**验收：** 四类状态可区分；重放无重复投影；普通执行回归不变。

## Task 5: 恢复 API 与完成边界

增加 resume API，返回最近未通过代码、Attempt 摘要和 starter code fallback。Attempt 不得自动写 `lesson_complete`；前端确认仍走唯一 analytics 写入口。补 request/attempt 元数据，避免 `code_run` 重复计数。

**验收：** 刷新可恢复；验证通过后仍未完成；确认动作后才完成。

## Task 6: 前端练习会话与三节课程体验

修改 `src/types/api.ts`、`src/api/playground.ts`、`src/stores/playground.ts`、`Playground.vue`、`LessonDetail.vue` 及 Vitest。初始化 starter code 或恢复结果；展示目标、提示、执行状态、验证状态和恢复入口；快照继续叫“快照”；通过后提供显式完成操作。

**验收：** 三节 tracer 走通；刷新后恢复；关键 store/API 测试通过。

## Task 7: 证据消费与收口

让推荐读取最近 Attempt 摘要；Agent 增加只读 attempt 摘要工具且不暴露完整代码；Dashboard 增加验证通过、最近尝试、可恢复练习和错误类别的最小真实指标。

**验收：** 推荐/Agent 能解释验证事实，不泄露跨 visitor 数据；首批验收和全量测试通过。

## 最终验证

每项运行 focused tests；Task 4 起同时跑 Playground、analytics、learner state 与 Agent 测试。最终运行后端全量 pytest、前端 Vitest、type-check/build、内容 lint、迁移 upgrade/downgrade，并手动走完三节 tracer 的浏览器流程。
