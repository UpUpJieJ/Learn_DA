# 阶段 4：内容与界面规模化（细化实施计划）

**状态：** 待执行
**制定日期：** 2026-08-01
**前置：** 阶段 0/1/2/3 已完成代码与测试闭环（后端 374 项、前端 47 项通过）
**范围说明：** 按用户决策，跳过所有需要服务器部署或使用 CI/CD 的交付项
（CI workflow、Mypy baseline、内容 lint 接入 CI、部署验收）；对应能力以本地
命令、单元测试和生产构建验证替代。

## 目标

让新增主题和修改核心页面不再依赖理解数千行文件：

1. Content Catalog 成为启动时校验、缓存的不可变内容索引，内容错误本地阻断；
2. 前端核心工作流从 1800+ 行页面抽成可测试的 composable 与展示组件；
3. 删除未被当前工作流使用的依赖与基础设施，生产依赖可映射到运行时用途。

## 已有基础，不重复建设

- `content_loader.py` 已有 frontmatter 解析、exercise fail-closed 校验、
  `lint_content()`（slug/exercise.id 重复）、catalog.yml 加载；
- `tests/unit/test_content_lint.py`（242 行）已覆盖基础 lint；
- `LearningRepository` 实例内有懒加载缓存；`KnowledgeRetriever` 已在
  lifespan 共享；embedding 已按内容哈希持久化；
- 前端已有 `learnerState` / `localState` / `playground` 三个 store，
  `playground.ts` 与 `markdown.ts` 已有 vitest 测试；
- 推荐冷却已落数据库表（`RecommendationCooldown`），不依赖 Redis。

## 设计约束

1. 内容索引在启动时构建一次并只读共享；任何模块不得再按请求扫描文件系统。
2. 内容错误必须显式失败（lint 不通过则加载失败），不得 print 警告后静默跳过。
3. 页面只消费 composable/组件接口，不重复实现数据请求与样式映射。
4. 删除依赖前先 grep 确认无引用；删除后全量回归必须通过。
5. 保留 SlowAPI 为唯一限流实现，删除自定义 Redis 限流中间件。
6. 不引入新基础设施；Redis 无真实运行时用例则不保留为生产依赖。

## 交付顺序

```text
Task 1 Content Catalog 深模块
  -> Task 2 前端工作流 composable 拆分（useLessonSession -> usePlaygroundSession
     -> RecommendationPanel -> AgentConversation）
  -> Task 3 删除失效基础设施
  -> Task 4 收口与本地验证
```

## Task 1：Content Catalog 深模块

**目的：** 内容在启动时 lint、校验并缓存为不可变索引，运行时不再逐请求读盘。

### 文件

- 新增 `app/core/content_catalog.py`（索引构建 + 引用图校验）
- 新增 `app/core/content_schemas.py`（Pydantic schema：catalog / frontmatter）
- 修改 `app/core/content_loader.py`（字段级校验、错误显式抛出）
- 修改 `app/learning/repository.py`（改为消费共享索引）
- 修改 `main.py`（lifespan 构建索引并做启动阻断）
- 新增 `scripts/content_lint.py`（本地 lint CLI）
- 扩展 `tests/unit/test_content_lint.py`、新增 `tests/unit/test_content_catalog.py`

### 实现

1. `content_schemas.py`：用 Pydantic 定义 `LessonFrontmatter`、`ExerciseDef`、
   `ContentCatalog`；校验 slug/id 唯一、track/category 存在、
   `prerequisite`/`recommended_next` 引用有效、课程图无非法环。
2. `content_catalog.py`：`build_content_index()` 一次加载课程 + 示例 + catalog，
   完成全部校验后返回只读索引；校验失败抛出带文件与字段的错误列表。
3. `content_loader.py`：`load_lesson_from_file` 的必需字段缺失从 print 警告
   改为显式失败；`lint_content` 扩展引用图检查。
4. `main.py` lifespan：启动时 `build_content_index()`，失败则记录并拒绝启动
   （fail closed）；索引存入 `app.state.content_index`。
5. `LearningRepository` 改为从注入的索引读取，不再自行扫盘；`load_catalog`
   返回缓存索引的 catalog。
6. `scripts/content_lint.py`：`python -m scripts.content_lint` 输出文件与
   字段级错误，非零退出码（替代 CI 校验的本地命令）。

### 测试

- 重复 slug / 重复 exercise.id / 引用不存在课程 / 非法环 / catalog track
  引用缺失均产生字段级错误；
- 索引构建失败时启动路径显式报错（不静默跳过）；
- 新增课程只需内容与 catalog 变更（集成测试验证既有路由仍返回新课程）；
- `LearningRepository` 复用同一索引实例（无重复扫描）。

### 验收

- 一次进程只扫描一次内容目录，后续请求零文件 IO；
- `python -m scripts.content_lint` 在错误内容上非零退出并指出文件/字段；
- 内容错误导致启动失败，而不是运行中缺课断链。

## Task 2：前端工作流模块加深

**目的：** 把 Playground（1805 行）、LessonDetail（1294 行）、Learning
（897 行）、AgentPanel（915 行）的核心工作流抽成可测试接口。

### 文件

- 新增 `learn_da_vue/src/composables/useLessonSession.ts`
- 新增 `learn_da_vue/src/composables/usePlaygroundSession.ts`
- 新增 `learn_da_vue/src/components/recommendation/RecommendationPanel.vue`
- 新增 `learn_da_vue/src/components/agent/AgentConversation.vue`
- 修改 `views/LessonDetail.vue`、`views/Playground.vue`、
  `views/Learning.vue`、`views/Dashboard.vue`、`components/agent/AgentPanel.vue`
- 新增各 composable/组件的 vitest 测试

### 实现

1. `useLessonSession(slug)`：课程加载、完成状态（learnerState store）、
   推荐刷新、`lesson_start`/`lesson_complete` 事件写入；LessonDetail 消费。
2. `usePlaygroundSession(lesson)`：草稿（localState）、attempt 执行
   （playground store）、快照、结果 Tab 选择；Playground 消费。
3. `RecommendationPanel.vue`：统一 Learning / LessonDetail / Dashboard 三处
   建议的渲染与交互，props/emit 稳定接口；页面只传数据。
4. `AgentConversation.vue`：从 AgentPanel 抽出消息状态、请求生命周期
   （AbortSignal、loading、feedback 提交）；embedded/floating 只保留布局适配
   在 AgentPanel。
5. 每个 composable 配套 vitest：加载态、完成/撤销写路径、草稿恢复、
   attempt 关联、推荐刷新去重。

### 验收

- Playground 与 LessonDetail 行数显著下降（核心工作流移入 composable）；
- 核心工作流可由 vitest 直接驱动，不依赖浏览器；
- 三处推荐建议渲染行为一致（同一组件实例化）。

## Task 3：删除失效基础设施

**目的：** 生产依赖都能映射到一个当前运行时用途。

### 文件

- 修改 `learn_da/pyproject.toml`、`uv.lock`
- 删除 `learn_da/app/utils/minio_service.py`
- 删除 `learn_da/app/middleware/rate_limit.py` 及 `middleware/__init__.py` 导出
- 删除 `learn_da/app/core/redis/`（`async_client.py`、`pool.py`）
- 修改 `learn_da/main.py`（移除 Redis lifespan/readiness 检查）
- 删除 `learn_da/package.json`（后端 ECharts 冗余声明）
- 修改 `docker-compose.app.yml`、`deploy/app.env.example`（移除 redis 服务与
  开关，仅文件清理，不做部署动作）
- 更新 `tests/test_health.py`（readiness 断言同步）

### 实现

1. 先 grep 确认 `minio_service`、`celery`、`fastapi_mail`、`paramiko`、
   `gevent`、`app.core.redis` 无业务引用后删除文件与依赖。
2. 限流二选一：删除自定义 Redis 限流中间件与导出，保留 SlowAPI
   （`app/utils/limiter.py`）。
3. Redis：推荐冷却已用数据库表，无队列/缓存真实用例 → 删除依赖与
   `app/core/redis/`，`main.py` 移除 Redis 启动检查与 readiness 项。
4. 删除后端 `learn_da/package.json`（仅重复声明前端 ECharts）。
5. 清理 compose/env 中的 redis 服务与 `REDIS_ENABLED` 开关（文件级清理）。

### 测试

- 删除后后端全量测试、`test_health`（redis 断言移除）通过；
- `uv.lock` 重新生成，`pip check` 无缺依赖；
- 全量启动（本地 uvicorn）正常，无 ImportError。

### 验收

- 所有生产依赖都能从 pyproject 映射到代码引用；
- 全项目不再出现 MinIO/Celery/邮件/Paramiko/Gevent/Redis 相关代码或配置。

## Task 4：收口与本地验证

- 更新 `docs/README.md`（状态与文档地图，标注跳过项）；
- 新增 `docs/phase4-content-and-ui-completion-summary.md`；
- 验证矩阵（全部本地执行）：后端全量 pytest、前端 vitest、type-check、
  生产构建、`scripts.content_lint`、启动冒烟（uvicorn + /live）。

## 明确跳过（按用户决策，不实施）

- 服务器部署验收（真实 Runner 执行三节样板课程）；
- CI workflow / GitHub Actions / 依赖审计流水线；
- Mypy baseline 检查器与 Black 收敛；
- 内容 lint 接入 CI（以本地 CLI + 单测替代）；
- 需要真实 Docker/Runner 环境的验证步骤。

## 完成定义

- 新增一条学习 track 只需内容与 catalog 变更，不修改页面硬编码；
- 内容错误在 `scripts.content_lint` 中给出文件与字段级错误，且启动 fail closed；
- Playground/LessonDetail 行数显著下降，核心工作流由 vitest 驱动；
- 全量测试（后端/前端）、type-check、生产构建、lint CLI、本地启动冒烟通过；
- 删除的依赖均先确认无引用，删除后无 ImportError；
- 不增加任何未被当前工作流使用的基础设施或依赖。
