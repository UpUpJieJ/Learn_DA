# 2026-10-31 重构审查收口

范围为 `refactor-review-2026-10-26.md` §8 三批修复及复查发现的直接相关回归。保留工作区开始时已有的未提交重构；没有推送或部署生产。

**后续发布已完成（2026-11-01）**：该段及以下 QA 记录描述重构收口时点；用户随后授权提交、停止 Hermes、清空历史并正式部署。生产验收29/29、全课程Docker76/76、最终空库14张业务表0行，详见 [部署记录](deployment-2026-11-01.md)。Runner 新增容器工作目录回归后为60项测试。

## 最终链路

`WorkspaceService → RunnerClient → Docker Runner（仅执行/观察）→ RunnerClient（后端可信判定）→ TaskAttempt`。

- API 出站剥离 refs、runtime、expect；容器与学员进程都拿不到答案。后端忽略沙箱 verdict，用原始内容定义重算。
- 表格使用受大小限制的 JSON，而非学员可构造的压缩 Arrow，避免宿主原生解码分配放大。校验列唯一、行宽、类型和值；SQL 标签按参考生成器口径归一化。
- Docker 长日志的 UTF-8 分块曾导致正确结果出现替换字符；driver 改 ASCII JSON escapes，中文仍在后端正常还原。
- Runner 原父子进程判定模式只保留供内部旧脚本兼容；正式 API 总是 observationMode。生产只允许 Docker，local 只在明确 development/test 环境放行。

## 已完成

1. 原 87 条自由表达式全部从 13 课移除；数据课用 schema/frame_equal/sql_rows/value，Python 函数用固定输入 call + 严格返回值比较。content loader 拒绝新增 expr_true。全部 35 个 refs 由参考解生成，无序表规范排序。
2. run 幂等按 visitor/session/operation/target/requestId 隔离；hint 可传 requestId，重试返回相同提示且只记一次。保存点、短事务行锁和重复写入恢复覆盖跨连接并发；运行时编辑不被旧结果标记为通过。
3. 复用 AnalyticsService 的幂等业务入口恢复开始、运行、整课完成与编辑后撤销完成。TaskAttempt 仍为教学证据，历史记录不重写。
4. workspace run/submit/hint 限流；默认与全局 IP 限流接入真实中间件。Windows drive 路径拒绝；compose 显式注入 production 与 session 预算。
5. SSE 跨工具轮累积文本，partial/取消/EOF 保留已吐内容；工具名不重复拼接，截断不当成功。60 秒 idle timeout + 180 秒单次 stream 总预算（含重试/退避）。
6. 前端跨课程异步响应按 generation 隔离；保存按格串行；执行等待上游草稿。离开页面先保存，失败取消导航，destroy 继续保存捕获的旧会话草稿。
7. 课程地图、报告与 Agent 排除失效通过记录；一次通过率统一用全历史 `tasksFirstTry / tasksAttempted`，不再由截断的卡点列表推测分母。UTC 计日和全历史跨度在界面明确标注。
8. 提示状态改为固定聚合查询，autosave 复用已加载快照数据；请求自有只读事务在等待 Runner 前释放。多轮模型调用复用一个 client，异常流也写审计并发 done。不可信代码/输出用数据边界与 JSON 引用隔离，不放进 system 指令；客户端 system 历史被丢弃。
9. AI 助手只暴露知识检索、学习进度、任务摘要三个只读 FC 工具；移除推荐下一课与出题入口，遵守不规划学习路线的项目约定。独立推荐服务与文档公开 API 仍保留。
10. UI lint 跨平台扫描 CSS/index、排除测试；基础组件零容忍、精确违规指纹禁止等量替换和扩大基线，当前基线为 0。修复正文对比度，清掉孤儿 token、无效主题/侧栏按钮、死模块、旧练习元数据和未使用 ECharts 依赖。
11. 组件补焦点循环/还原/滚动锁、加载时保留焦点并阻止操作、属性与描述透传、stdout/stderr 同显和播报、HTTP 剪贴板兜底、最多 5 条 Toast 与定时器清理。Lab 补请求代次、真实耗时、表预览/截断提示；报告与课程地图补任务深链、重试状态和全完成复习入口。
12. 相对路径仍执行内容 lint；生成器强制单线程并阻断孤儿 refs。比较拒绝数字字符串跨型，支持表内 NaN/Inf 且无穷大必须同号同值；Decimal38 按精确位数校验，Float32 校验可表示性，SQL 校验列宽及列名。
13. Docker stdout/stderr 分开读取，local 异常杀进程后 wait 回收。默认沙箱改为版本 tag，进程首次执行解析并固定 image ID；严格跨重启复现可配置镜像 digest，升级依赖时必须重建镜像并重新生成 refs。
14. 任务当前验证使用独立持久化标记：普通运行与下游重放不能复活旧通过。跨进程旧请求晚到不改写更新状态，新增历史尝试按执行开始时间排序；旧完成投影通过既有幂等事件撤销对齐，不改历史记录。

## 复测

- 本地后端、Runner、前端全量测试及 type-check/UI lint；内容 lint、数据集/refs 字节校验。
- 最终本地全量结果：后端 **604 passed**、Runner **59 passed（无 xfail）**、前端 **172 passed**，另 UI lint 规则测试 **4 passed**。type-check、UI lint、内容/数据集/refs 校验全部通过，视觉基线为 0。
- 新 `scripts/verify_observation_runner.py` 通过真实 HTTP Runner/Docker 验证 13 课 38 任务的起步代码必失败、参考解必通过，共 76 项；不写学习数据库。
- `tests/test_workspace_observations.py` 逐课验证相同 JSON 序列化、类型契约及后端判定，防止内容测试绕过 wire 行为。
- 真实 Docker 另外验证自定义相等对象不能通过 call，以及伪造 marker 不能隐藏真实异常。前三门课新增独立 `sorted_by` 检查，容忍并列行但拒绝乱序结果。
- 最终真实 HTTP/Docker 全量复测 **76/76**；原五条 PoC **5/5 符合安全预期**。PoC 脚本已同步长度帧协议，缺少 driver 结果不会再被误记为安全通过。
- Linux 临时 Node 容器实跑 `npm ci --include=dev` 与 `npm run build` 成功；Windows 本机 esbuild 临时文件删除问题仍是既有环境限制。浏览器核对首页、报告空态和 Lab 真实执行（含耗时与表预览）。
- `deploy/acceptance.sh` 在隔离 QA 数据库 + 真实 Docker Runner + 真实 LLM 上 **29/29**。脚本已从“至少 3 条旧断言”改为核验当前必须的 schema/frame 两条及所有结果通过，避免课程迁移造成误报。
- 新 marker 迁移后再次验收仍为 **29/29**；数据库从空库到 head、已有 QA 库从 c7 到 d8 均实际升级成功。最终唯一 head 为 `d8a42b6f9013`。独立最终代码复查未发现新的重要回归；复查未代替测试。

## 发布与兼容事项

- 启动新版后端前执行 Alembic upgrade，新增迁移 `c7d31a8e9f02`（提示幂等）与 `d8a42b6f9013`（当前任务验证标记）；历史提示/尝试保留。旧活动工作区默认未验证，需要每个任务重新提交一次，之后普通运行不会再把历史通过误恢复。前后端与 Runner 需配套更新，旧 Runner 无 observations 时任务判定 fail closed。
- 收口时未发布；上述测试使用独立 QA 数据库和临时 Runner。后续正式部署及生产复测见上方部署记录。
- 退役旧 Dashboard 的六个 analytics GET，以及重复的 `/lessons/all`。`/catalog`、`/lessons/categories`、`/recommendations` 是有文档/测试的公开接口，未因“无前端消费者”误删；推荐内部仍需的历史聚合保留。N-16 是审查时已删除的历史组件，无当前实现需修。
- CI 的 GitHub 账单锁定仍是账户外部条件，本轮按约定执行本地全门禁与 Linux 构建。
- 收口时未暂停 Hermes。正式发布阶段已按用户要求停止 Hermes 用户服务，未停止其他业务容器。
