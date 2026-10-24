# AGENTS.md — Learn DA 项目上下文

> 面向 AI 代理/新会话的项目事实速查。最后更新：2026-10-24。

## 项目是什么

交互式数据分析学习平台（Polars / DuckDB / Python 编程基础）：教程 + 在线代码实操 + AI 学习助手。
技术栈：Vue 3 + Vite + TS + Pinia（`learn_da_vue`）、FastAPI + Python 3.12（`learn_da`）、独立 Runner 沙箱服务（`learn_da_runner`）。
**无账号体系**：签名匿名 session cookie 标识学习者；学习进度唯一权威在服务端 LearnerState。

## 当前状态（截至 2026-10-24）

- 2026-07-14 路线图的**阶段 0-4 全部完成**（安全执行门禁 / 统一学习事实 / 可验证练习闭环 / 证据驱动 Agent / 内容与界面规模化），内部 Alpha，已部署生产环境。
- **旧练习体系已下线**（2026-10-24）：13 门课 frontmatter 的 `exercise:` 块全部删除，`app/practice/` 的 validator / repository / service / router / schemas 与 `POST /playground/exercises/*`（resume/attempts/stats）、`POST /playground/format`、`GET /analytics/practice-stats`、`GET /analytics/recommended-lessons` 一并移除；`exercise_attempts` 表**冻结只读**（`app/practice/models.py` 仍登记给 Alembic，历史数据留存，不要再写入）。任务判定与教学证据全部走 `task_attempts`。`app/practice/` 现在只剩断言 DSL v2（`assertion_runtime.py` + `assertions.py`）。
- **生产部署验收已改写为工作区链路**（2026-10-24，19/19 全绿）：真实 Runner 执行 → 起步代码必判失败 → 参考解逐格通过 → 同 requestId 幂等 → 进度/报告接口 → Agent 三场景（`no_evidence` / `passed_unconfirmed` / 跨访客隔离）→ 改上游代码下游失效 → `/analytics/track` 幂等；复测用 `bash deploy/acceptance.sh`（默认 `http://127.0.0.1:8000`，可用 `LEARN_DA_BASE_URL` 覆盖）。旧的 17 项练习链路验收记录见 `learn_da/docs/production-acceptance-2026-08-17.md`（已过时，只作历史）。
- **CI 暂缓**（2026-08-21）：最小 CI 门禁已编写并本地验证（后端 pytest + content_lint + Runner 测试 + 前端 vitest/type-check/build），但 GitHub 账户因账单锁定无法运行 Actions，workflow 文件已暂时移除；账单解锁后用 `git checkout ac779dc -- .github/workflows/ci.yml` 恢复。在此之前，**提交前必须本地手动跑全部测试**（回到阶段 4 时的约定）。
- **P1 收尾完成**（2026-08-21）：① 回流建议信号移除对 CodeSnapshot 表的读取（快照功能已删，死表不再参与推荐打分，只留 code_runs/ai_helps）；② Agent 分级提示 hint_level 改为**服务端真实连续求助计数**（按课程统计 AgentInteraction，1-2 次 L1 / 3-4 次 L2 / 5+ L3），不再信任客户端 history（可伪造/清空）；无 repo/身份/课程或查询失败时降级为 history 估算。
- **学习工作区改版 M0–M4 + 页面重构 P0–P4 已完成**（2026-10-21/22）：确定性数据集 `learn_da/content/datasets/ecommerce/`（`scripts/build_datasets.py` 生成，`--check` 校验字节一致）+ 断言 DSL v2 骨架（`app/practice/assertion_runtime.py` 求值、`app/practice/assertions.py` 校验与生成尾巴，四型 `expr_true`/`frame_equal`/`schema`/`sql_rows`）+ 后端工作区表与 API（`app/workspace/`）+ Runner 会话执行（`POST /v1/sessions`）+ **前端三栏工作区**（`learn_da_vue/src/views/LessonWorkspace.vue`，路由 `/lesson/:slug`）。样板课最初是 `03-polars-groupby`；**M4 已把全部 13 门课迁到工作区格式**（每课 3 个任务、3–11 条断言，课程正文按数据课 260–330 行 / 纯 Python 课 180–240 行加厚），写作规范见 `learn_da/docs/workspace-content-spec.md`，参考解在 `learn_da/scripts/solutions/<slug>.py`（由 `learn_da/tests/test_workspace_content.py` 逐课校验「起步代码必失败 + 参考解必全过」）。
- **前端页面重构 P0–P4 已完成**（2026-10-22）：语义 token + `src/components/ui/` 基础组件层 + `scripts/ui_lint.mjs` 基线检查（P0）；页面只剩 5 个路由——`/`(Home)、`/learn`(CourseMap 课程地图)、`/lesson/:slug`(LessonWorkspace)、`/report`(Report 学习报告)、`/lab`(Lab 自由实验室)；**旧的 `/learn/:slug`、`/playground`、`/dashboard` 已下线**，`Learning.vue`/`LessonDetail.vue`/`Playground.vue`/`Dashboard.vue` 与 `useLessonSession`/`usePlaygroundSession` 已删除。`/workspace/progress` 与 `/workspace/report` 提供进度与报告数据。
- 设计稿见 `learn_da/docs/learning-workspace-redesign-2026-10-21.md`（§11.2 M1+M2、§11.3 M3、§11.4 M4+P1/P3/P4、§15 页面重构）。
- **AI 助手 E0/E1 已完成**（2026-10-23/24）：E0 把证据源从冻结的 `exercise_attempts` 改到 `task_attempts`（含断言 `actual`），E1 把助手接进工作区右栏（`learn_da_vue/src/components/workspace/WorkspaceAssistant.vue`）：ambient 证据卡直接渲染 `store.runs[cell].assertions`（0 请求 0 token）、chat 走 `POST /api/v1/agent/chat`、**非流式**（「正在思考…」→ 整段落地，去掉原来的伪流式）。`hint_level` 现在真的进 prompt（`prompts.build_hint_directive`）。架构是「确定性策略层 + 单一 LLM 表达层」：判定全在 Python，模型只负责讲人话。**命名统一为「AI 助手」**（2026-10-24 用户要求；组件 `WorkspaceAssistant.vue`、prompt 里自称「通用学习助手」），且**不提供「下一步该练什么」引导**——任务顺序由服务端任务列表权威给出，模型不自行规划学习路线（`SYSTEM_PROMPT` 已明写）。
- 测试基线：后端 **442 项** pytest、Runner **39 项**、前端 **115 项** vitest 全绿（2026-10-24 更新，含旧练习体系下线后的净变化：删掉 validator/repository/resume/playground-exercise 四个文件与 `test_agent_evidence.py`，`test_practice_evidence.py` 改名为 `test_workspace_evidence_consumption.py`；`deploy/acceptance.sh` 19/19 通过）。`npm run build` 在本机因 esbuild 临时文件删除被环境拦截（见「已知问题与坑」）。
- 2026-08-17 修复：**明文 HTTP 下会话 cookie 带 Secure 导致访客身份丢失**（生产验收发现）——新增 `PUBLIC_SCHEME` 配置（默认 http，compose 注入；启用 HTTPS 时在 `deploy/app.env` 改 https），cookie Secure 属性跟随对外协议。
- 最近一批重构（2026-08-16）：
  - LLM 只有一套配置 `LLM_*`；**`FALLBACK_LLM_*` 已删除**（2026-10-21，历史遗留的假兜底：只在主配置为空时生效，主配置存在但调用失败时不会切换）。调用失败时走 `usedFallback` 确定性降级，不会换 key。
  - 修复明文 HTTP 下 `crypto.randomUUID` 崩溃：前端统一走 `src/lib/uuid.ts` 的 `randomId()`（兼容非安全上下文）。
  - **删除示例体系**（`/examples` API、content/examples、Playground 示例选择器）；课程自带 `codeExample` 保留。
  - **删除快照功能**（保存按钮/快照 tab//analytics/snapshot(s) 端点）；`CodeSnapshot` 表保留。回流建议信号已于 2026-08-21 移除对该表的读取，表仅供历史数据留存。
  - （历史）练习 validator 加固：polars-basics 改 `dataframe_rows`、duckdb-sql-foundations 改 `stdout_exact`，堵住"全表输出也判通过"的漏洞。该体系已于 2026-10-24 整体下线。
  - **内容 YAML fail-closed 加固**：frontmatter 坏 YAML / 缺失 / 根节点非映射、catalog.yml 损坏均显式报错并阻断启动（`parse_frontmatter` 不再静默返回空），修复坏课程被静默跳过"凭空消失"的问题。改课程 frontmatter 后仍建议跑 `scripts/content_lint.py` 确认课程数 = 13。

## 高频命令

```bash
# 后端（learn_da/，venv 在 learn_da/.venv，包管理用 uv）
cd learn_da && .venv/Scripts/python.exe -m pytest -q          # 全部测试
.venv/Scripts/python.exe scripts/content_lint.py               # 内容校验（课程/catalog）
.venv/Scripts/python.exe scripts/build_datasets.py --check     # 数据集字节一致性校验（不带 --check 则重新生成）

# 前端（learn_da_vue/）
cd learn_da_vue && npm test -- --run      # vitest
npm run type-check                        # vue-tsc
npm run lint:ui                           # 视觉规范检查（语义 token / 圆角 / 阴影）
npm run check                             # type-check + lint:ui 一起跑
npm run build                             # 生产构建

# Runner（learn_da_runner/，venv 在 learn_da_runner/.venv）
cd learn_da_runner && .venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m uvicorn runner.main:app --host 127.0.0.1 --port 8080

# 13 课内容全量校验（起步代码必须判不通过、参考解必须全过；不需要后端与 Runner）
cd learn_da && .venv/Scripts/python.exe -m pytest tests/test_workspace_content.py -q

# 工作区（改版 M1）端到端自检：创建会话 → 参考解 → 逐格执行 → 提交任务
cd learn_da && .venv/Scripts/python.exe scripts/verify_workspace.py --base-url http://127.0.0.1:8000

# 生产验收（本地或目标主机都能跑，需 curl + 能执行的 python3/python）
bash deploy/acceptance.sh                 # 默认打 http://127.0.0.1:8000，会写入一批验收数据
LEARN_DA_BASE_URL=http://<host>:8000 bash deploy/acceptance.sh   # 打远端
```

## 关键架构约定（改动前必读）

- **学习状态唯一写入口**是 `POST /analytics/track`；`/learner-state/*` 只读。前端所有完成/撤销/开始带幂等 eventId。
- **任务尝试（TaskAttempt）是教学证据核心**：工作区提交任务时自动落库（代码 + `verdict` + 每条断言的 `actual`），喂推荐与 Agent 五态教学反馈。`verdict` 是 Runner 原始结论（`passed`/`assertion_failed`/`execution_failed`），`status` 是教学口径（`passed`/`failed`/`skipped`），**别互相顶替**。本地草稿在 `session_cells.code`（800ms 去抖 PUT）。
- Agent 判断**只信服务端证据**，客户端自报 stdout/stderr 不作为事实来源；`teachingFeedback` 的 state/nextAction 由服务端决定。
- **Agent 证据链（2026-10-24 收口后）**：`app/agent/evidence.py` 的 `AgentEvidenceResolver(workspace_repo=...)` **只读 `task_attempts`**（旧 `exercise_attempts` 回落分支已删，无 workspace 的课直接返回 `no_evidence`）；`derive_workspace_state(verdict, status)` 推导五态，`next_action` 用 `next_task`（`confirm_lesson` 已废）。`context.currentCode` 与最近提交的代码不一致时证据块会显式提醒（`code_matches_editor`），否则模型会拿旧代码反驳断言结果。FC 工具是 `get_task_summary`（不是 `get_exercise_summary`）。模型调用失败返回 `FALLBACK_UNAVAILABLE_CONTENT`「AI 助手暂时不可用」，**不再编造预置话术**。
- 内容体系：`content/catalog.yml`（topics/tracks）+ `content/lessons/*.md` frontmatter；启动时构建共享 ContentIndex，**lint 错误 fail closed 阻断启动**（含 frontmatter 坏 YAML、catalog.yml 损坏，均显式报错不静默跳过）；课程图（prerequisites）校验无环。
- **任务判定只有断言 DSL v2**（`app/practice/assertion_runtime.py` 求值 + `app/practice/assertions.py` 校验/生成尾巴）：四型 `expr_true` / `frame_equal` / `schema` / `sql_rows`，失败必须回传 `actual`（截断 500）。`schema.columns` 默认"必须包含"、`exact: true` 才要求完全一致。执行接口的 `code` 上限是 5000 字符，所以运行时尾巴按路径加载（`render_assertion_source(..., runtime_path=...)`），别用默认的内联模式（约 10KB，会 422）。旧的 `stdout_exact` / `stdout_contains` / `dataframe_rows` validator 已随练习链路删除，**不要再按那些类型写课程**。
- **课程数据集可复现**：`content/datasets/**` 一律由 `scripts/build_datasets.py` 生成（固定 seed），不要手改；改生成器后重跑脚本，`--check` 用 sha256 比对仓库文件。
- **工作区（改版 M1/M2）**：表在 `app/workspace/models.py`（`lesson_sessions` / `session_cells` / `run_events` / `task_attempts`），API 前缀 `/api/v1/workspace`，Runner 侧走 `POST /v1/sessions`（`learn_da_runner/runner/session.py` + `session_driver.py` 顺序重放）。
  - 新业务模块的 router 必须写进 `ENABLED_APP_MODULES`（`config/settings.py` 默认值 + `.env` + `docker-compose.app.yml`），漏配就是**全 404**（`learner_state` 当年踩过）。
  - 严格顺序语义：改第 k 格代码 → 第 k 格自身与其后所有格置 `stale`；已通过的任务若所在格不再是 `ok`，视图状态回 `todo`（需复核），**不改历史 `TaskAttempt`**。
  - 执行幂等：`run_events.payload` 存完整 `RunResponse.model_dump(by_alias=True)`，同 `requestId` 重放直接还原（含 `taskStatus`），别再改回存原始 Runner 报文。
  - 服务层提交事务用 `WorkspaceService._commit()`：测试外层事务（`db.info["external_transaction"]`）下只 flush，直接 `db.commit()` 会炸 "closed transaction"。
- **工作区前端（改版 M3/P2）**：`src/views/LessonWorkspace.vue` + `src/stores/workspace.ts` + `src/api/workspace.ts`，路由 `/lesson/:slug`（唯一课程入口，深链 `?task=<taskId>`）；`/learn` 是 `CourseMap.vue` 课程地图，按 `GET /workspace/progress` 渲染。`LessonSummary.hasWorkspace` 仍由 frontmatter 有无 `workspace:` 决定（现 13 课全为 true）。改代码后 **800ms 去抖**才 PUT 落库；提交任务前先 flush 该格；`runCell`/`submitTask` 先占 `runningCellId`/`submittingTaskId` 再 flush（否则连点会并发跑两次）；`requestId` 用 `lib/uuid` 的 `randomId()`。
- **Runner 的执行后端二选一**（`learn_da_runner/runner/settings.py`）：`RUNNER_PROVIDER=docker`（默认，生产唯一选择，容器隔离）或 `local`（开发用宿主解释器：需 `RUNNER_ALLOW_LOCAL_EXECUTION=1`，且 `RUNNER_ENV`/`APP_ENV` 为 production 时 `build_provider()` 直接拒绝启动）。local **不是安全边界**（无网络隔离、无只读 fs），只用于本机没有 Docker 时跑通闭环；它沿用同一套超时/输出上限，并把 CRLF 归一成 LF、用 `-X utf8` 对齐 Linux 沙箱的文本行为。
- Runner 的 token 解析顺序：进程环境 `RUNNER_TOKEN` > `.env`（`runner/settings.py`），所以只靠 `.env` 的本地跑法也能通过鉴权。
- `RATE_LIMIT_ENABLED=False` 必须真的关掉限流：开关同步到 `limiter.enabled`（`app/utils/limiter.py`）。只在 `main.py` 跳过 `setup_limiter_middleware()` 是不够的——按路由的 `@limiter.limit(...)` 仍会独立计数并抛 429（2026-10-21 修复，`tests/unit/test_rate_limit_toggle.py` 守着）。
- **前端 UI 只有一套语义 token**（`src/assets/styles/main.css` 的 `@theme`）：颜色 `brand-* / ok-* / warn-* / err-* / ink-* / surface-* / line`，圆角仅 `rounded-card|control|pill`，阴影仅 `shadow-card|pop`。不要在页面里直接写 raw palette（`blue-500`、`emerald-100` 等），`npm run lint:ui` 会用基线（`scripts/ui_lint.baseline.json`）拦住新增违规，`src/components/ui/**` 零容忍。
- **基础组件在 `src/components/ui/`**（`AppButton` / `AppCard` / `AppInput` / `StatusPill` / `CodeOutput` / `EmptyState` / `ConfirmDialog` / `ToastHost`）：新页面直接用，不要手写第二套按钮或自造状态药丸；网络页面三态用 `useAsyncState`，瞬时反馈用 `useToast()`，危险操作用 `ConfirmDialog`（不用 `window.confirm`），空态必须带 CTA。

## 部署与运维

- 生产：**单机双 compose 模式**（`docker-compose.app.yml` + `docker-compose.runner.yml` 一起加载），项目在服务器 `/app/Learn_DA`，数据卷 `learn_da_data`（SQLite），migrate 容器自动跑 Alembic。对外协议由 `PUBLIC_SCHEME` 声明（当前明文 HTTP=http；上 HTTPS 后改 https，cookie 自动加 Secure）。
- **日常更新一句话**：本地 `bash deploy/push-deploy.sh`（推 GitHub→上传 bundle 兜底→ssh 触发服务器 `deploy/update.sh`）。只更服务器：`ssh root@<ip> /app/Learn_DA/deploy/update.sh`。
- 服务器地址与凭据**不入库**：IP 见本地 `~/.ssh/config` 的 Host 条目（root 免密已配）；密钥在服务器上的 `deploy/app.env` / `runner.env`（未跟踪）。
- 同机还有用户其他容器（agent-customer 全家桶、redis01/02）——**部署操作不得触碰**，只操作 learn_da compose 项目。

## 已知问题与坑

1. black 对部分存量文件有格式意见（版本差异、不在近期改动行上）——**勿顺手重排**，避免污染 diff。
2. 本地推 GitHub 经常被重置：可用本地代理 `git -c http.proxy=http://127.0.0.1:7897 push origin main`（代理没开就靠 bundle 路径）。
3. Git Bash 会把 `/` 开头的命令行参数改写成 Windows 路径——传服务器绝对路径时加 `MSYS_NO_PATHCONV=1`。
4. ZCode 内嵌浏览器（IAB）不持久化 cookie，每个请求都是新 visitor——**测身份相关功能（进度/尝试列表）用 curl 带 cookie jar 或真实浏览器**。
5. 服务器内存 3.6G 无 swap：前端镜像构建是内存峰值点，其余容器同时跑时留意。
6. 明文 HTTP 部署下浏览器安全上下文 API 受限（randomUUID、剪贴板等）——新前端代码生成 ID 一律用 `lib/uuid` 的 `randomId()`，勿直接调 `crypto.randomUUID`。
7. 课程 frontmatter 的标量字段（如 hints 条目）含“冒号+空格”会被 YAML 解析成 mapping 而被 fail-closed 拦截——此类条目整体加双引号；改完跑 `scripts/content_lint.py`。
8. **本地开发的 API 地址必须走 vite 代理**：`learn_da_vue/.env.development` 的 `VITE_API_BASE_URL=/api/v1`（同源）。若写死成 `http://127.0.0.1:8000/api/v1`，页面（`localhost:5173`）到 API 就是**跨站**请求，`SameSite=Lax` 的会话 cookie 不随请求发送 → 每个请求都是新访客，工作区/进度会报「会话不存在」。
9. **本机 `npm run build` 会被 esbuild 临时文件权限拦住（环境问题，不是代码）**：报 `[vite:esbuild-transpile] remove C:\Users\<user>\AppData\Local\Temp\esbuild-<hash>: Access is denied.`。已排除 tailwind 插件 / minify / target / manualChunks / TEMP 位置；同一份依赖在本机 M3 时构建成功过，属 DSH/Codex 类 Windows 沙箱（minifilter）或实时杀毒拒绝子进程删除自己写的临时文件。**验证构建请在普通终端或服务器上跑**；本机 CI 门禁只保证 `npm run type-check` + `npm run lint:ui` + `npm test`。


## 文档地图

- 迭代路线图与阶段验收标准：`learn_da/docs/iteration-roadmap-2026-07-14.md`
- 阶段完成总结：`learn_da/docs/phase3-evidence-agent-completion-summary.md`、`phase4-content-and-ui-completion-summary.md`
- 部署细节：`deploy/README.md`；配置项：根 `README.md` 配置表；生产验收记录：`learn_da/docs/production-acceptance-2026-08-17.md`
- 改版设计与阶段记录：`learn_da/docs/learning-workspace-redesign-2026-10-21.md`
- 课程内容写作规范（`workspace:` 块、断言规则、正文结构）：`learn_da/docs/workspace-content-spec.md`
