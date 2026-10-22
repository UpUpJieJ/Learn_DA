# Learn DA -- 交互式数据分析学习平台

> 一个轻量化、无 LangChain、原生 OpenAI Agent 驱动的学习平台，主打「教程学习 + 在线代码实操 + AI 一对一答疑/纠错」，覆盖 Polars、DuckDB 等现代数据分析工具与编程基础，从入门到实战。

---

## 项目简介

**Learn DA** 是一个以数据分析为核心的交互式学习网站。平台提供结构化教程、可实时运行的代码工作区（多单元格 + 任务级自动判定），帮助用户在浏览器中边学边练，快速掌握现代数据分析工具的核心用法与最佳实践。主题与学习路径可按需扩展，不绑定某一组技术栈。

核心特性：

- **教程学习**：覆盖 Polars、DuckDB、组合实战与 Python 编程基础等主题，共 13 门课，课程地图按专题展示进度与「继续上次」入口。
- **任务式工作区**：每门课是一个多单元格工作区（读数据 → 逐步加工 → 提交任务），提交时由服务端断言判定对错，失败会回传实际值帮你定位；结果依赖上游，改了上游会标「结果已过期」。
- **实验室（`/lab`）**：自由沙盒，不挂课程数据、不判定，用来随手试代码；`Ctrl/⌘+Enter` 运行。
- **学习报告（`/report`）**：只用真实提交记录计算——已通过任务、完成课程、连续学习、能力分布、常见卡点、最近提交。
- **AI 教练（改版中）**：Agent 后端（证据驱动的五态反馈 + 只读工具链）仍在，聊天面板在页面重构期间暂时下线，将随工作区内的分档介入（失败卡片 / 阶梯提示 / 对话）一起接回。
- **安全执行策略**：代码执行只走独立 Runner 服务，默认在无网络、只读文件系统、非 root、带内存/CPU/进程数与超时限制的一次性容器里运行；Runner 不可用时后端明确返回 503，不回退本地执行。
- **无登录本地模式**：无需账号即可使用核心功能；学习进度以服务端匿名会话为准，界面偏好与工作区草稿另存当前浏览器本地。

---

## 技术架构

项目采用**前后端分离 + 微模块解耦**架构：

| 层级 | 技术栈 | 职责 |
|------|--------|------|
| 前端交互层 | Vue 3 + Vite + TypeScript + TailwindCSS + Pinia | 用户界面、教程渲染、代码编辑、结果展示、Agent 对话 |
| 后端服务层 | FastAPI + Python 3.12 + Uvicorn | 接口中转、业务逻辑、数据持久化、Agent 调度、沙箱通信 |
| AI Agent 层 | 原生 OpenAI API（Function Calling） | 概念解释、代码生成、代码校验、对比分析、实战案例推荐 |
| 安全执行层 | 独立 Runner 服务 + Docker 容器隔离（默认） / 宿主解释器（仅开发） | 运行用户代码，限制网络、资源与超时；生产只用容器隔离 |
| 数据存储层 | SQLite（SQLAlchemy 异步 + Alembic 迁移） | 学习事件、练习尝试、交互审计与学习状态 |

---

## 目录结构

```
.
├── README.md                 # 本文件
├── docker-compose.app.yml    # 应用服务器编排（Web + Backend）
├── docker-compose.runner.yml # 专用 Runner 服务器编排
├── deploy/                   # 部署环境变量模板与运维文档
├── learn_da/                 # 后端（Backend）
│   ├── main.py               # FastAPI 应用入口
│   ├── pyproject.toml        # Python 依赖与工具配置
│   ├── Dockerfile            # 主应用镜像
│   ├── Dockerfile.sandbox    # 代码沙箱镜像
│   ├── config/               # 配置管理（Pydantic Settings）
│   ├── app/                  # 业务模块
│   │   ├── agent/            # AI Agent（证据解析、FC 工具、提示词、交互审计）
│   │   ├── analytics/        # 学习事件追踪、画像投影、日统计
│   │   ├── core/             # 数据库、内容索引、会话、异常处理
│   │   ├── learner_state/    # 服务端学习进度投影（唯一权威状态源）
│   │   ├── learning/         # 教程内容接口与规则推荐
│   │   ├── playground/       # 代码执行接口（练习执行 / 自由沙盒）
│   │   ├── workspace/        # 学习工作区（会话 / 单元格外 / 任务判定 / 进度与报告）
│   │   ├── practice/         # 可验证练习（尝试模型、旧 validator、v2 断言 DSL）
│   │   ├── sandbox/          # 沙箱执行调度（Runner client）
│   │   ├── middleware/       # CORS、安全头、访问日志中间件
│   │   └── utils/            # 通用工具、自动路由注册、SlowAPI 限流
│   ├── migrations/           # Alembic 数据库迁移
│   ├── scripts/              # 内容校验、数据集生成、端到端自检
│   ├── tests/                # 测试用例（pytest）
│   └── content/              # 教程静态内容（含 datasets/ 课程数据集）
│
└── learn_da_runner/          # 代码执行服务（Docker / local 两种后端）
└── learn_da_vue/             # 前端（Frontend）
    ├── package.json          # Node 依赖
    ├── vite.config.ts        # Vite 构建配置（含 API 代理）
    ├── tsconfig.json         # TypeScript 配置
    └── src/
        ├── main.ts           # 应用入口
        ├── App.vue           # 根组件
        ├── router/           # Vue Router 路由
        ├── stores/           # Pinia 状态管理（learnerState 服务端为准、localState 离线缓存）
        ├── api/              # Axios API 封装（agent / learning / playground / analytics）
        ├── views/            # 页面级组件
        │   ├── Home.vue          # 今日（首页 + 继续上次）
        │   ├── CourseMap.vue     # /learn 课程地图
        │   ├── LessonWorkspace.vue # /lesson/:slug 三栏工作区
        │   ├── Report.vue        # /report 学习报告
        │   ├── Lab.vue           # /lab 自由实验室
        │   └── NotFound.vue
        ├── components/       # 可复用组件
        │   ├── ui/           # 基础组件层（AppButton / AppCard / AppInput / StatusPill / CodeOutput / EmptyState / ConfirmDialog / ToastHost）
        │   ├── layout/       # 布局组件（Navbar 等）
        │   ├── home/         # 首页组件（ContinueStrip 继续上次）
        │   ├── agent/        # AI Agent 面板（AgentPanel.vue，改版期间待接回）
        │   └── recommendation/ # 统一推荐卡片（RecommendationPanel.vue，待接回）
        ├── composables/      # 组合式函数（useAsyncState / useToast / useAgentConversation）
        ├── types/            # TypeScript 类型定义
        └── assets/           # 样式与静态资源（assets/styles/main.css 定义语义 token）
```

---

## 快速开始

### 环境要求

- **Python**：>= 3.12（后端）
- **Node.js**：`^20.19.0 || >=22.12.0`（前端）
- **Docker**（生产必需：代码一律在 Runner 的沙箱容器里执行）
- 本地开发没有 Docker 时可用 Runner 的 `RUNNER_PROVIDER=local` 模式跑通流程（见「本地无 Docker」小节，**仅开发用**）

### 后端启动

```bash
cd learn_da

# 1. 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv sync --extra dev

# 2. 配置环境变量（可选，也可使用默认值）
cp .env.example .env       # 若存在示例文件
# 编辑 .env 设置 LLM_API_KEY、LLM_BASE_URL 等

# 3. 运行数据库迁移（首次启动）
alembic upgrade head

# 4. 启动开发服务器
python main.py
# 或使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

后端默认运行在 `http://127.0.0.1:8000`，API 前缀为 `/api/v1`。

### 前端启动

```bash
cd learn_da_vue

# 1. 安装依赖
npm install

# 2. 启动开发服务器
npm run dev
```

前端默认运行在 `http://127.0.0.1:5173`（**只监听 IPv6，用 `localhost` 访问**，`127.0.0.1` 会连接被拒），已配置代理将 `/api` 请求转发至后端 `http://127.0.0.1:8000`。

> `.env.development` 里的 `VITE_API_BASE_URL` 必须是 `/api/v1`（走代理、同源）。写成 `http://127.0.0.1:8000/api/v1` 会让请求变成跨站，`SameSite=Lax` 的会话 cookie 不随请求发送，每个请求都被当成新访客（工作区会报「会话不存在」，进度也存不住）。

#### 前端 UI 约定（2026-10-21 起）

- **只用语义 token**：颜色 `brand-* / ok-* / warn-* / err-* / ink-* / surface-* / line`，圆角 `rounded-card|control|pill`，阴影 `shadow-card|pop`，全部定义在 `src/assets/styles/main.css` 的 `@theme`。页面里不要直接写 `blue-500`、`emerald-100` 这类原色。
- **基础组件在 `src/components/ui/`**：`AppButton` / `AppCard` / `AppInput` / `StatusPill` / `CodeOutput` / `EmptyState` / `ConfirmDialog` / `ToastHost`。新页面直接复用，不要再手写一套按钮。
- **三态与反馈**：网络页面用 `useAsyncState`（idle/loading/ready/empty/error），瞬时反馈用 `useToast()`，危险操作用 `ConfirmDialog`（不用 `window.confirm`），空态必须给 CTA。
- **提交前跑规范检查**：`npm run lint:ui`（或 `npm run check` = type-check + lint:ui）。存量违规有基线（`scripts/ui_lint.baseline.json`，当前 63 个文件 / 225 处），新增违规会让命令以非零码退出；`src/components/ui/**` 零容忍。线上收紧基线后不要随手 `--update-baseline`。

### Runner 启动（代码执行，必需）

工作区执行、练习判定、Agent 的证据链都依赖 Runner；后端拿不到 Runner 时执行接口会返回 503。

```bash
cd learn_da_runner
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv sync
cp .env.example .env                                # 写入 RUNNER_TOKEN（与 learn_da/.env 一致）

# 有 Docker：构建沙箱镜像后按默认 docker provider 启动
docker build -f ../learn_da/Dockerfile.sandbox -t polars-duckdb-sandbox:latest ../learn_da
uvicorn runner.main:app --host 127.0.0.1 --port 8080
```

**本地无 Docker**（仅开发自测，不是安全边界）：Runner 可用宿主解释器执行代码，
需要在 `learn_da_runner/.env` 里显式开启，并在 `learn_da/.env` 配同一个 `RUNNER_TOKEN`：

```ini
RUNNER_TOKEN=<与 learn_da/.env 相同>
RUNNER_ENV=development
RUNNER_PROVIDER=local
RUNNER_ALLOW_LOCAL_EXECUTION=1
RUNNER_LOCAL_PYTHON=<解释器绝对路径，需装好 polars/duckdb/pyarrow>
```

`RUNNER_ENV=production` 时 Runner 拒绝以 local 方式启动；生产必须用 docker provider。

一键自检（13 门课的练习：starter 必须判不通过、标准解必须判通过）：

```bash
cd learn_da
.venv/Scripts/python.exe scripts/verify_exercises.py --base-url http://127.0.0.1:8000
```

> 跑全量 13 课会触发执行接口频率限制（默认 10 次/分钟），自检时把后端以
> `RATE_LIMIT_ENABLED=False` 启动（该开关会连同按路由的限流一起关掉），或分批执行。

### Docker Compose 生产部署

生产环境分为两台服务器：应用服务器运行 Web 与 Backend，专用 Runner
服务器运行用户代码的沙箱。不要在应用服务器挂载 Docker socket。

完整步骤见 [`deploy/README.md`](deploy/README.md)。最简命令如下：

```bash
# Runner 服务器：先构建受限沙箱与 Runner
cp deploy/runner.env.example deploy/runner.env
docker compose --env-file deploy/runner.env -f docker-compose.runner.yml \
  --profile sandbox build
docker compose --env-file deploy/runner.env -f docker-compose.runner.yml \
  up -d --build runner

# 应用服务器：RUNNER_URL 指向 Runner 的私网地址
cp deploy/app.env.example deploy/app.env
docker compose --env-file deploy/app.env -f docker-compose.app.yml up -d --build
```

只有一台服务器时，可在同一条 Compose 命令中加载两份编排，并在
`deploy/app.env` 设置 `RUNNER_URL=http://runner:8080`、在
`deploy/runner.env` 设置 `RUNNER_BIND_ADDRESS=127.0.0.1`。Runner 不会
对公网暴露，但它仍持有该主机 Docker socket，因此这是资源受限时的折中方案。

镜像基于 **Debian 12 (bookworm)**，基础镜像标签为 `python/node/nginx:*-slim`（避免部分镜像站对 `*-bookworm-slim` 返回 403）。构建时默认 **APT 清华源**、`pip/uv` **阿里 PyPI**、`npm` **npmmirror**。拉取失败见 [`deploy/DOCKER_MIRROR.md`](deploy/DOCKER_MIRROR.md)。

---

## 核心配置说明

后端配置通过环境变量或 `.env` 文件管理，关键项如下：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | 运行环境 |
| `PUBLIC_SCHEME` | `http` | 对外协议（http/https），决定会话 cookie 是否带 Secure；启用 HTTPS 时改 `https` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./learn_da.db` | 数据库连接串 |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | 前端跨域白名单 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | — / — / `gpt-4o-mini` | LLM 配置（只有这一套；未配置 key 或调用失败时 Agent 确定性降级，不会切换到备用 key） |
| `RATE_LIMIT_ENABLED` | `true` | 是否启用接口限流（关掉后全局与按路由的限流一并失效） |
| `RECOMMENDATION_CODE_RUNS_THRESHOLD` | `5` | 触发回补建议的代码运行次数阈值 |
| `RECOMMENDATION_AI_HELPS_THRESHOLD` | `3` | 触发回补建议的 AI 求助次数阈值 |
| `RECOMMENDATION_REVIEW_COOLDOWN_SECONDS` | `86400` | 同一用户同一课程重复触发回补建议的冷却时间 |
| `RECOMMENDATION_RESUME_ABSENCE_THRESHOLD_DAYS` | `3` | 触发回流建议的未学习天数阈值 |
| `RUNNER_URL` | — | 专用 Runner 的私网 URL，生产环境必填 |
| `RUNNER_TOKEN` | — | Backend 与 Runner 共用的内部认证密钥，至少 32 字符 |
| `SESSION_SECRET` | — | Backend 匿名会话签名密钥，生产环境至少 32 字符 |
| `ENABLED_APP_MODULES` | `learning,playground,agent,analytics,learner_state,practice,workspace` | 启用的业务模块 |

完整配置定义见 [`learn_da/config/settings.py`](learn_da/config/settings.py)。

---

## 主要功能模块

### 1. 教程学习（Learning）

- 分模块展示 Polars、DuckDB 及联用实战教程。
- 支持章节导航、代码示例高亮与步骤化学习。
- 课程接口：
  - `GET /api/v1/lessons`：获取课程列表，支持 `category`、`difficulty`、`keyword` 查询参数。
  - `GET /api/v1/lessons/{slug}`：获取课程详情。
  - `GET /api/v1/lessons/categories`：获取课程分类统计。

### 2. 学习工作区与实验室

- **工作区**（`/lesson/<slug>`）：一门课 = 一个多单元格工作区，右侧是任务清单。点「运行」或「提交任务」时，服务端按顺序重放前 k 个单元格，再对目标格求值断言；格子结果依赖上游，改上游后下游标「结果已过期」。
- **实验室**（`/lab`）：自由沙盒，不挂课程数据集、不做判定，用来随手试代码。
- 代码编辑区为带行号的 textarea（暂未接入 Monaco）；`Ctrl/⌘+Enter` 运行。
- 用户代码提交至后端，**一律转交 Runner 执行，Runner 不可用时明确拒绝**（fail-closed，不回退本地/模拟执行）。
- 工作区草稿按 `{lesson, cell}` 保存在当前浏览器本地（800ms 去抖后同步到服务端会话）。

### 3. AI Agent 助手

> 状态：Agent 后端（证据链 + FC 工具 + 五态反馈）可用，聊天面板在页面重构期间暂时下线，将随工作区内的分档介入一起接回（见 `learn_da/docs/learning-workspace-redesign-2026-10-21.md` §12）。

- 原本悬浮于页面右下角，随时唤起。
- **学习证据驱动**（阶段 3）：Agent 的练习判断完全基于服务端数据库证据
  （ExerciseAttempt 执行/验证状态 + LearnerState 课程完成），客户端自报的
  stdout/stderr 不作为事实来源。每次回答附带结构化 `teachingFeedback`
  （五态 + 下一步动作 + 分级提示），LLM 不得覆盖服务端权威字段。
- Agent 工具集：
  - **概念解释**：讲解 Polars / DuckDB 核心 API 与原理。
  - **代码生成**：生成可直接运行的示例代码。
  - **代码校验**：检查语法错误、逻辑错误与 API 误用。
  - **对比分析**：Polars vs Pandas、DuckDB vs 传统 SQL。
  - **实战案例**：数据分析、清洗、批量查询的实战代码推荐。
- 对话上下文保留短期记忆，支持单轮深度问答。

### 4. 学习状态与匿名会话

- 平台不提供账号、登录、注册或 JWT 认证；使用签名匿名 session cookie 标识学习者。
- 学习进度以服务端工作区会话与任务尝试为准（`/api/v1/workspace/*`）；旧 `POST /analytics/track` 事件链仍在，用于历史数据。
- 编辑器偏好、工作区草稿等纯 UI 状态仍保存在当前浏览器本地。
- 清理浏览器数据或更换设备后，服务端进度不受影响；离线缓存会丢失但可从服务端恢复。

---

## 添加新的学习主题

平台已支持通过内容配置扩展学习主题。新增主题通常只需要两步：

1. 在 [`learn_da/content/catalog.yml`](learn_da/content/catalog.yml) 中添加 `topics` 和 `tracks`。
2. 在 [`learn_da/content/lessons`](learn_da/content/lessons) 中新增 Markdown 课程，并填写 `topic`、`category`、`track`、`prerequisites`、`recommended_next`、`skill_tags` 等 frontmatter。

最小课程示例：

```yaml
---
id: 12
slug: python-functions
title: Python 函数入门
topic: programming
category: python
track: python_basics
difficulty: beginner
tags: [python, function]
prerequisites: []
recommended_next: []
skill_tags: [function, parameter, return_value]
is_review_friendly: true
is_branch_point: false
---
```

新增课程后，`/api/v1/catalog` 会返回新的主题/路径，`/api/v1/lessons?topic=programming&track=python_basics` 可按主题和路径筛选课程，前端学习中心会优先使用 catalog 动态生成专题入口。

### 课程数据集与断言 DSL（改版 M0）

课程用到的数据不再内联在正文里，而是放在 [`learn_da/content/datasets`](learn_da/content/datasets)：

```bash
cd learn_da
.venv/Scripts/python.exe scripts/build_datasets.py           # 重新生成（固定 seed，字节可复现）
.venv/Scripts/python.exe scripts/build_datasets.py --check    # 只校验仓库文件与生成器产物是否一致
```

**不要手改数据集文件**——它们和 `manifest.json` 里的 sha256 由生成器决定，改动会在 `--check` 和测试里报 drift。

判定侧新增了 v2 断言 DSL（`learn_da/app/practice/assertion_runtime.py` + `learn_da/app/practice/assertions.py`），
支持 `expr_true` / `frame_equal` / `schema` / `sql_rows` 四种断言，失败时回传被截断的 `actual` 供诊断。
注意执行接口的 `code` 上限是 5000 字符，追加断言时要用按路径加载的紧凑尾巴：

```python
from app.practice.assertions import render_assertion_source

footer = render_assertion_source(assertions, runtime_path="/app/app/practice/assertion_runtime.py")
```

设计与阶段计划见 [`learn_da/docs/learning-workspace-redesign-2026-10-21.md`](learn_da/docs/learning-workspace-redesign-2026-10-21.md)。

### 学习工作区（改版 M1/M2/M3）

课程 frontmatter 可带 `workspace:` 块（多 cell + 任务 + 断言），后端提供会话式 API：

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/workspace/sessions` | 按 `lessonSlug` 创建/复用会话，返回单元格、任务、数据集 |
| `GET` | `/api/v1/workspace/sessions/{id}` | 会话快照（格子状态、任务状态、`staleFrom`） |
| `PUT` | `/api/v1/workspace/sessions/{id}/cells/{cellId}` | 改代码（后续格子级联失效） |
| `POST` | `/api/v1/workspace/sessions/{id}/cells/{cellId}/run` | 重放式执行到该格（`requestId` 幂等） |
| `POST` | `/api/v1/workspace/sessions/{id}/tasks/{taskId}/submit` | 提交任务（落 `task_attempts`，返回断言明细） |
| `GET` | `/api/v1/workspace/progress` | 课程级进度（课程地图用） |
| `GET` | `/api/v1/workspace/report` | 学习报告（指标 / 能力分布 / 常见卡点 / 最近提交） |

后端把这些请求转成 Runner 的 `POST /v1/sessions`（顺序重放 + 单进程）。**13 门课全部已迁到工作区格式**
（每课 3 个任务、3–11 条断言），内容写法见
[`learn_da/docs/workspace-content-spec.md`](learn_da/docs/workspace-content-spec.md)。
端到端自检（需后端与 Runner 都在跑）：

```bash
cd learn_da
.venv/Scripts/python.exe scripts/verify_workspace.py --base-url http://127.0.0.1:8000
```

前端页面（改版 P1/P3/P4 之后只剩 5 个）：

| 路由 | 页面 | 说明 |
|---|---|---|
| `/` | `Home.vue` | 今日：首页 + 顶部「继续上次」条（1 击回到上次任务） |
| `/learn` | `CourseMap.vue` | 课程地图：按 track 分组的进度与「开始/继续/复习」 |
| `/lesson/:slug` | `LessonWorkspace.vue` | 三栏工作区：左任务列表、中单元格流（运行 / 提交任务）、右任务目标 |
| `/report` | `Report.vue` | 学习报告 |
| `/lab` | `Lab.vue` | 自由实验室（不挂课程数据、不判定） |

工作区示例：`http://localhost:5173/lesson/polars-groupby`（深链 `?task=<taskId>` 可直接定位任务）。
编辑自动去抖 800ms 落库；改第 k 格后其自身与后续格标为「需执行」，上游改动会让已通过任务回到「需复核」。
旧的 `/learn/:slug`、`/playground`、`/dashboard` 已下线（对应 `LessonDetail.vue` / `Playground.vue` /
`Learning.vue` / `Dashboard.vue` 已删除）。

---

## 测试

Phase 3 学习建议系统已经完成收口，整体设计、交付物与验证结果见
[`learn_da/docs/phase3-evidence-agent-completion-summary.md`](learn_da/docs/phase3-evidence-agent-completion-summary.md)。

```bash
cd learn_da

# 运行全部测试
pytest

# 运行单元测试
pytest -m unit

# 运行集成测试
pytest -m integration

# 覆盖率报告
pytest --cov=app --cov=services --cov-report=html
```

前端：

```bash
cd learn_da_vue
npm test -- --run      # vitest（17 文件 / 113 项）
npm run type-check     # vue-tsc
npm run lint:ui        # 视觉规范（新增违规即失败）
npm run build          # 生产构建
```

---

## 部署建议

1. **开发环境**：按「快速开始」分别启动前后端，使用 SQLite 即可。
2. **测试/预发布**：
   - 使用 Docker Compose 统一部署。
   - 仍是单机 SQLite（代码里没有 MySQL 适配，别按旧文档去改驱动）。
3. **生产环境**：
   - 使用 `docker-compose.app.yml` 部署 Web 与 Backend，使用
     `docker-compose.runner.yml` 在专用主机部署 Runner。
   - 仅允许应用服务器通过私网访问 Runner 的 8080 端口；禁止公网暴露。
   - 配置 HTTPS 反向代理（同时把 `PUBLIC_SCHEME` 改成 https）、限流策略和持久化数据卷。
   - 多个 Backend 副本需要共享数据库，当前实现只支持单实例 + SQLite。

---

## 技术亮点

- **无 LangChain**：Agent 层完全基于原生 OpenAI Function Calling 实现（只读工具集、模型不参与推荐排序、硬步数上限），零冗余依赖，调用链路可控，成本更低；离线评测集验证意图准确率 90.2%（关键词基线 43.9%）。
- **学习证据驱动**：Agent 练习判断基于服务端数据库证据（五态教学反馈），客户端自报状态不可影响教学结论；`AgentInteraction` 表以 request_id 幂等关联 ai_help，相同请求重放不重复计数，不持久化完整代码/prompt/token/cookie。
- **安全沙箱**：用户代码不直接运行在主服务进程，Docker 容器隔离 + 白名单库 + 资源配额 + 超时销毁，保障服务安全。
- **模块热插拔**：通过 `ENABLED_APP_MODULES` 按需启用 learning / playground / agent 模块，便于功能灰度与维护。
- **自动路由注册**：后端基于约定自动扫描注册 APIRouter，减少手动维护路由表的成本。
- **前后端同构限流**：后端基于 SlowAPI 实现细粒度限流（Agent 对话、代码执行独立配额）。


---

## License

本项目为内部学习项目，具体开源协议待定。
