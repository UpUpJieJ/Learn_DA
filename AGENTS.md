# AGENTS.md — Learn DA 项目上下文

> 面向 AI 代理/新会话的项目事实速查。最后更新：2026-08-16。

## 项目是什么

交互式数据分析学习平台（Polars / DuckDB / Python 编程基础）：教程 + 在线代码实操 + AI 学习教练。
技术栈：Vue 3 + Vite + TS + Pinia（`learn_da_vue`）、FastAPI + Python 3.12（`learn_da`）、独立 Runner 沙箱服务（`learn_da_runner`）。
**无账号体系**：签名匿名 session cookie 标识学习者；学习进度唯一权威在服务端 LearnerState。

## 当前状态（截至 2026-08-16）

- 2026-07-14 路线图的**阶段 0-4 全部完成**（安全执行门禁 / 统一学习事实 / 可验证练习闭环 / 证据驱动 Agent / 内容与界面规模化），内部 Alpha，已部署生产环境。
- 测试基线：后端 **379 项** pytest、前端 **71 项** vitest 全绿；**无 CI**（Task 9 当时有意跳过），提交前需本地手动跑。
- 最近一批重构（2026-08-16）：
  - LLM 兜底配置改名：`LLM_*` 为主配置，`FALLBACK_LLM_*` 为兜底（`effective_llm_*` 统一解析）。
  - 修复明文 HTTP 下 `crypto.randomUUID` 崩溃：前端统一走 `src/lib/uuid.ts` 的 `randomId()`（兼容非安全上下文）。
  - **删除示例体系**（`/examples` API、content/examples、Playground 示例选择器）；课程自带 `codeExample` 保留。
  - **删除快照功能**（保存按钮/快照 tab//analytics/snapshot(s) 端点）；`CodeSnapshot` 表保留（回流建议读历史数据）。
  - 练习 validator 加固：polars-basics 改 `dataframe_rows`、duckdb-sql-foundations 改 `stdout_exact`，堵住"全表输出也判通过"的漏洞。

## 高频命令

```bash
# 后端（learn_da/，venv 在 learn_da/.venv，包管理用 uv）
cd learn_da && .venv/Scripts/python.exe -m pytest -q          # 全部测试
.venv/Scripts/python.exe scripts/content_lint.py               # 内容校验（课程/catalog）

# 前端（learn_da_vue/）
cd learn_da_vue && npm test -- --run      # vitest
npm run type-check                        # vue-tsc
npm run build                             # 生产构建
```

## 关键架构约定（改动前必读）

- **学习状态唯一写入口**是 `POST /analytics/track`；`/learner-state/*` 只读。前端所有完成/撤销/开始带幂等 eventId。
- **练习尝试（ExerciseAttempt）是教学证据核心**：练习执行自动落库（代码+验证结果），喂推荐与 Agent 五态教学反馈。本地草稿（localStorage，按 `lesson:{slug}`/`default`）是另一条独立持久化。
- Agent 练习判断**只信服务端证据**，客户端自报 stdout/stderr 不作为事实来源；`teachingFeedback` 的 state/nextAction 由服务端决定。
- 内容体系：`content/catalog.yml`（topics/tracks）+ `content/lessons/*.md` frontmatter；启动时构建共享 ContentIndex，**lint 错误 fail closed 阻断启动**；课程图（prerequisites）校验无环。
- 练习 validator 白名单：`stdout_exact` / `stdout_contains` / `dataframe_rows`（`app/practice/validator.py`）。**不要用 stdout_contains 判定"必须排除某些行"的场景**——它无法发现多余行。
- 生产执行 fail-closed：代码执行只走 Runner（`RUNNER_URL`），Runner 不可用时明确拒绝，不回退本地/mock。

## 部署与运维

- 生产：**单机双 compose 模式**（`docker-compose.app.yml` + `docker-compose.runner.yml` 一起加载），项目在服务器 `/app/Learn_DA`，数据卷 `learn_da_data`（SQLite），migrate 容器自动跑 Alembic。
- **日常更新一句话**：本地 `bash deploy/push-deploy.sh`（推 GitHub→上传 bundle 兜底→ssh 触发服务器 `deploy/update.sh`）。只更服务器：`ssh root@<ip> /app/Learn_DA/deploy/update.sh`。
- 服务器地址与凭据**不入库**：IP 见本地 `~/.ssh/config` 的 Host 条目（root 免密已配）；密钥在服务器上的 `deploy/app.env` / `runner.env`（未跟踪）。
- 同机还有用户其他容器（agent-customer 全家桶、redis01/02）——**部署操作不得触碰**，只操作 learn_da compose 项目。

## 已知问题与坑

1. **`parse_frontmatter` 对坏 YAML 静默返回空** → 该课程被 lint/加载静默跳过（曾导致一节课凭空消失）。改动课程 frontmatter 后务必跑 `content_lint.py` 并确认课程数 = 13。待修：解析失败应显式报错。
2. black 对部分存量文件有格式意见（版本差异、不在近期改动行上）——**勿顺手重排**，避免污染 diff。
3. 本地推 GitHub 经常被重置：可用本地代理 `git -c http.proxy=http://127.0.0.1:7897 push origin main`（代理没开就靠 bundle 路径）。
4. Git Bash 会把 `/` 开头的命令行参数改写成 Windows 路径——传服务器绝对路径时加 `MSYS_NO_PATHCONV=1`。
5. ZCode 内嵌浏览器（IAB）不持久化 cookie，每个请求都是新 visitor——**测身份相关功能（进度/尝试列表）用 curl 带 cookie jar 或真实浏览器**。
6. 服务器内存 3.6G 无 swap：前端镜像构建是内存峰值点，其余容器同时跑时留意。
7. 明文 HTTP 部署下浏览器安全上下文 API 受限（randomUUID、剪贴板等）——新前端代码生成 ID 一律用 `lib/uuid` 的 `randomId()`，勿直接调 `crypto.randomUUID`。

## 文档地图

- 迭代路线图与阶段验收标准：`learn_da/docs/iteration-roadmap-2026-07-14.md`
- 阶段完成总结：`learn_da/docs/phase3-evidence-agent-completion-summary.md`、`phase4-content-and-ui-completion-summary.md`
- 部署细节：`deploy/README.md`；配置项：根 `README.md` 配置表
