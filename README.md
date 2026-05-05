# Learn DA —— Polars + DuckDB 交互式学习平台

> 一个轻量化、无 LangChain、原生 OpenAI Agent 驱动的专项学习平台，主打「教程学习 + 在线代码实操 + AI 一对一答疑/纠错」，专注解决 Polars 和 DuckDB 入门、进阶与实战痛点。

---

## 项目简介

**Learn DA** 是围绕 **Polars** 与 **DuckDB** 构建的交互式学习网站。平台提供结构化教程、可实时运行的代码 Playground，以及内嵌 AI Agent 助手，帮助用户在浏览器中边学边练，快速掌握现代数据分析工具的核心用法与最佳实践。

核心特性：

- **教程学习**：覆盖 Polars 专项、DuckDB 专项、Polars + DuckDB 联用实战与常见问题汇总。
- **交互式 Playground**：左侧 Monaco Editor（VSCode 同款）编写代码，右侧实时查看运行结果与数据预览，支持一键运行、清空与本地草稿体验。
- **AI Agent 助手**：固定右下角悬浮窗，基于原生 OpenAI Function Calling 实现，支持问答、代码生成、错误排查、API 对比与示例讲解，全程无跳转。
- **安全沙箱执行**：用户提交的 Polars / DuckDB 代码在 Docker 容器中隔离运行，限制资源与超时，禁止恶意操作。
- **无登录本地模式**：无需账号即可使用核心功能；学习进度与界面偏好保存在当前浏览器本地。

---

## 技术架构

项目采用**前后端分离 + 微模块解耦**架构：

| 层级 | 技术栈 | 职责 |
|------|--------|------|
| 前端交互层 | Vue 3 + Vite + TypeScript + TailwindCSS + Pinia | 用户界面、教程渲染、代码编辑、结果展示、Agent 对话 |
| 后端服务层 | FastAPI + Python 3.12 + Uvicorn | 接口中转、业务逻辑、数据持久化、Agent 调度、沙箱通信 |
| AI Agent 层 | 原生 OpenAI API（Function Calling） | 概念解释、代码生成、代码校验、对比分析、实战案例推荐 |
| 安全沙箱层 | Docker 容器隔离 | 隔离执行用户代码，资源配额与超时控制 |
| 数据存储层 | SQLite（默认）/ MySQL + Redis（可选） | 教程内容、运行数据与可选缓存 |

---

## 目录结构

```
.
├── README.md                 # 本文件
├── learn_da/                 # 后端（Backend）
│   ├── main.py               # FastAPI 应用入口
│   ├── pyproject.toml        # Python 依赖与工具配置
│   ├── docker-compose.yml    # 容器编排（App + Redis）
│   ├── Dockerfile            # 主应用镜像
│   ├── Dockerfile.sandbox    # 代码沙箱镜像
│   ├── config/               # 配置管理（Pydantic Settings）
│   ├── app/                  # 业务模块
│   │   ├── agent/            # AI Agent 核心（工具、提示词、服务、路由）
│   │   ├── core/             # 数据库、Redis、异常处理
│   │   ├── learning/         # 教程内容接口
│   │   ├── playground/       # Playground 业务逻辑
│   │   ├── sandbox/          # 沙箱执行调度
│   │   ├── middleware/       # CORS、安全、访问日志、限流中间件
│   │   └── utils/            # 通用工具、自动路由注册、标准响应
│   ├── migrations/           # Alembic 数据库迁移
│   ├── tests/                # 测试用例（pytest）
│   └── content/              # 教程静态内容
│
└── learn_da_vue/             # 前端（Frontend）
    ├── package.json          # Node 依赖
    ├── vite.config.ts        # Vite 构建配置（含 API 代理）
    ├── tsconfig.json         # TypeScript 配置
    └── src/
        ├── main.ts           # 应用入口
        ├── App.vue           # 根组件
        ├── router/           # Vue Router 路由
        ├── stores/           # Pinia 状态管理（本地学习进度、偏好、UI 状态）
        ├── api/              # Axios API 封装（agent / learning / playground）
        ├── views/            # 页面级组件
        │   ├── Home.vue
        │   ├── Learning.vue
        │   ├── LessonDetail.vue
        │   ├── Playground.vue
        │   └── NotFound.vue
        ├── components/       # 可复用组件
        │   ├── layout/       # 布局组件（Navbar 等）
        │   ├── editor/       # 代码编辑器相关
        │   ├── playground/   # Playground 交互组件
        │   ├── agent/        # AI Agent 面板（AgentPanel.vue）
        │   └── common/       # 通用组件
        ├── composables/      # Vue 组合式函数
        ├── types/            # TypeScript 类型定义
        └── assets/           # 样式与静态资源
```

---

## 快速开始

### 环境要求

- **Python**：>= 3.12（后端）
- **Node.js**：`^20.19.0 || >=22.12.0`（前端）
- **Docker & Docker Compose**（可选，用于沙箱与一键部署）

### 后端启动

```bash
cd learn_da

# 1. 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv sync --extra dev

# 2. 配置环境变量（可选，也可使用默认值）
cp .env.example .env       # 若存在示例文件
# 编辑 .env 设置 OPENAI_API_KEY、LLM_API_KEY 等

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

前端默认运行在 `http://127.0.0.1:5173`，已配置代理将 `/api` 请求转发至后端 `http://127.0.0.1:8000`。

### Docker Compose 一键启动

```bash
cd learn_da

# 构建并启动主应用（含 SQLite 本地存储）
docker-compose up -d app

# 若需要 Redis 缓存
docker-compose --profile redis up -d

# 构建沙箱镜像（用于隔离执行用户代码）
docker-compose --profile sandbox build
```

---

## 核心配置说明

后端配置通过环境变量或 `.env` 文件管理，关键项如下：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | 运行环境 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./learn_da.db` | 数据库连接串 |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | 前端跨域白名单 |
| `OPENAI_API_KEY` | — | OpenAI API 密钥 |
| `OPENAI_BASE_URL` | — | 自定义 OpenAI 兼容接口地址 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 默认 LLM 模型 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | — | 备用 LLM 配置 |
| `REDIS_ENABLED` | `false` | 是否启用 Redis |
| `RATE_LIMIT_ENABLED` | `true` | 是否启用接口限流 |
| `SANDBOX_DOCKER_ENABLED` | `false` | 是否启用 Docker 沙箱执行 |
| `ENABLED_APP_MODULES` | `learning,playground,agent` | 启用的业务模块 |

完整配置定义见 [`learn_da/config/settings.py`](learn_da/config/settings.py)。

---

## 主要功能模块

### 1. 教程学习（Learning）

- 分模块展示 Polars、DuckDB 及联用实战教程。
- 支持章节导航、代码示例高亮与步骤化学习。

### 2. Playground 代码实操

- 基于 Monaco Editor，支持 Python 语法高亮与自动补全。
- 用户代码提交至后端，可选择本地模拟执行或 Docker 沙箱隔离执行。
- 返回执行结果、标准输出、数据表格预览与报错信息。

### 3. AI Agent 助手

- 悬浮于页面右下角，随时唤起。
- Agent 工具集：
  - **概念解释**：讲解 Polars / DuckDB 核心 API 与原理。
  - **代码生成**：生成可直接运行的示例代码。
  - **代码校验**：检查语法错误、逻辑错误与 API 误用。
  - **对比分析**：Polars vs Pandas、DuckDB vs 传统 SQL。
  - **实战案例**：数据分析、清洗、批量查询的实战代码推荐。
- 对话上下文保留短期记忆，支持单轮深度问答。

### 4. 本地学习状态

- 平台不提供账号、登录、注册或 JWT 认证。
- 学习进度、最近访问课程、编辑器偏好等状态保存在当前浏览器本地。
- 清理浏览器数据、更换浏览器或更换设备后，本地学习状态不会自动同步。

---

## 测试

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

---

## 部署建议

1. **开发环境**：按「快速开始」分别启动前后端，使用 SQLite 即可。
2. **测试/预发布**：
   - 使用 Docker Compose 统一部署。
   - 按需启用 Redis 提升缓存性能。
   - 迁移至 MySQL 以支持并发写入。
3. **生产环境**：
   - 务必启用 `SANDBOX_DOCKER_ENABLED=true`，确保用户代码在 Docker 沙箱中运行。
   - 配置 Nginx / Traefik 反向代理，SSL 终止。
   - 配置 `RATE_LIMIT_ENABLED=true` 与慢速限流策略，防止接口滥用。
   - 使用独立 Redis 与 MySQL/PostgreSQL，持久化日志与数据卷。

---

## 技术亮点

- **无 LangChain**：Agent 层完全基于原生 OpenAI Function Calling 实现，零冗余依赖，调用链路可控，成本更低。
- **安全沙箱**：用户代码不直接运行在主服务进程，Docker 容器隔离 + 白名单库 + 资源配额 + 超时销毁，保障服务安全。
- **模块热插拔**：通过 `ENABLED_APP_MODULES` 按需启用 learning / playground / agent 模块，便于功能灰度与维护。
- **自动路由注册**：后端基于约定自动扫描注册 APIRouter，减少手动维护路由表的成本。
- **前后端同构限流**：后端基于 SlowAPI 实现细粒度限流（Agent 对话、代码执行独立配额）。


---

## License

本项目为内部学习项目，具体开源协议待定。
