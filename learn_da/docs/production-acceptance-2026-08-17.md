# 生产部署验收记录（2026-08-17）

**状态：** 通过（自动化 17/17，遗留浏览器目测项见文末）
**环境：** 单机双 compose（`43.142.89.100`，明文 HTTP :80），后端镜像含提交 `91f478c`
**脚本：** [`../../deploy/acceptance.sh`](../../deploy/acceptance.sh)（可重复执行，每次以全新匿名访客写入一批验收数据）

## 背景

Phase 3 / Phase 4 完成总结中遗留的"服务器部署验收"（三节样板课程真实
Runner 执行 + Agent 反馈 + Dashboard 指标）在本次完成。验收从服务器本机
经 nginx → backend → runner 全链路执行。

## 验收结果（17 项全部通过）

| 组 | 检查项 | 结果 |
|---|---|---|
| A1 | ContentIndex 构建，13 门课程可列出 | PASS |
| A2 | 签名匿名会话 cookie 签发（无 Secure，适配明文 HTTP）+ 进度可读 | PASS |
| A3 | 三节样板课正确答案经真实 Runner 执行并验证通过（`polars-basics` dataframe_rows / `duckdb-sql-foundations` stdout_exact / `python-functions` stdout_exact） | PASS |
| A4 | 全表输出（未筛选）被 `dataframe_rows` 判 failed —— 2026-08-16 validator 加固在生产有效 | PASS |
| A5 | 相同 requestId 重放返回同一 attemptId，不新建 Attempt | PASS |
| A6 | `lesson_start`/`lesson_complete` 上报、进度投影正确、相同 eventId 重放不重复计数 | PASS |
| A7 | Agent 五态：新访客 `no_evidence`；通过 Attempt `passed_unconfirmed` + nextAction；失败 Attempt `verification_failed`；伪造 attemptId 无法获取他人证据（跨访客隔离） | PASS |
| A8 | `practice-stats` 指标字段齐全，passedExercises=3，`helpThenPassRate`/`unresolvedFailures` 正常返回 | PASS |

## 验收中发现并修复的缺陷

**会话 cookie 在明文 HTTP 下失效（严重）：**
`main.py` 原先 `https_only=settings.APP_ENV == "production"`，而部署为明文
HTTP——`Set-Cookie` 带 `Secure` 属性被浏览器拒收，匿名访客身份逐请求丢失，
进度 / Attempt / Agent 反馈全部断链（首轮验收 A2–A8 大面积失败的根因）。
修复：新增 `PUBLIC_SCHEME` 配置（默认 `http`，compose 显式注入；启用 HTTPS
时在 `deploy/app.env` 改 `https`），cookie Secure 属性跟随对外协议；补 2 项
回归测试（明文 HTTP 下 Set-Cookie 不得带 Secure；scheme 校验器拒绝非法值），
后端测试 388 → 390 项。

## 仍需人工目测（脚本无法覆盖）

- AgentPanel 状态徽章 / 证据摘要 / 下一步按钮在真实浏览器中的渲染（注意用
  真实浏览器或 curl cookie jar，内嵌浏览器不持久化 cookie）；
- 课程页 → Playground → 完成建议 → 返回确认的跨页面工作流；
- 移动端布局目测。

## 复测方式

```bash
# 服务器上（或任何可访问目标主机的机器，需 curl + python3）
bash deploy/acceptance.sh
LEARN_DA_BASE_URL=http://other-host bash deploy/acceptance.sh
```
