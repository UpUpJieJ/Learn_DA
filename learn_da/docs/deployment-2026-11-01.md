# 2026-11-01 全新部署记录

用户明确授权提交全部重构、停止 Hermes、清空 Learn DA 历史并部署。应用源码版本为 `9efd651221abc50385d1550b3266a072579f18d7`，已推送 GitHub。后续文档提交不改变运行镜像。

日常更新、配置、备份恢复和故障处理统一查阅[部署与运维手册](../../deploy/README.md)，本文保留这次上线的事实快照。

## 最终状态

- 目标为用户确认的 SSH 别名 `lavm`，项目 `/app/Learn_DA`，Compose 项目 `learn_da`。此主机未发现旧 Learn DA checkout、容器或数据卷，因此从新卷安装。
- Backend、Runner 健康，Web 对外提供 HTTP；Runner 仅绑定宿主 `127.0.0.1:8080`，Backend 通过内部网络 `http://runner:8080` 访问。公网首页、课程地图、报告、Lab、课程深链与 13 课 API 已验证。
- 生产验收 `deploy/acceptance.sh` **29/29**，包含实际 Docker 执行、失败/通过、幂等、失效、提示、真实 LLM 与经过 Nginx 的 SSE；流式回答未走 fallback。
- 在生产 Backend 容器内执行 `scripts/verify_observation_runner.py`，经生产 Runner 容器与真实沙箱执行，13 课 38 个任务的起步/参考解 **76/76**。
- 验收后停写、归档验收数据库，再重建空库并迁移。最终 head `d8a42b6f9013`，**14 张业务表共 0 行**；包括冻结的 exercise_attempts、历史快照表与所有任务/提示/Agent/学习事件表。共享运行目录 0 个残留条目。
- Hermes 用户服务 `hermes-gateway.service` 为 `inactive`、`MainPID=0`，`UnitFileState=enabled`；本次仅停止，未关闭开机启动。其他业务容器未被停止或删除。
- 最后资源核对约 1.1 GiB 可用内存、3.7 GiB 可用磁盘；本机已有 swap。

## 部署中实际修复

1. 发布脚本拒绝未提交文件，要求明确 SSH 目标；上传完整 bundle 与新 updater，校验指定 commit。顺序构建并利用内容缓存重建沙箱，避免失败重试使用旧 tag。
2. 停止写入后冷备份项目卷；只允许删除带正确 project/logical-volume 标签的两个自有卷。Runner 就绪后才迁移、启动 Backend/Web，失败中止并保留日志。
3. 双 env 文件会让 Runner 超时覆盖 Backend，现分别配置 Backend 30 秒与 Runner 20 秒的会话预算。
4. 旧 `nginx:1.27-slim` 在目标镜像通道无法解析，改为已拉取并成功构建的同版本 Debian `nginx:1.27`。
5. 旧 Dockerfile 忽略后端锁文件，首次构建发现未测试的依赖升级。现后端冻结导出 uv.lock 并验证哈希，Runner 使用基于已测试环境生成的通用哈希锁。实际镜像的 Backend 80 个、Runner 32 个依赖逐项匹配锁。
6. 生产 Runner 自身也是容器，私有 /tmp 不能直接交给宿主 Docker bind。改用宿主与 Runner 同路径的 `/var/lib/learn_da/runner-work`，700、65532:0，配置错误启动即拒绝；沙箱只接收单次请求目录的只读挂载。回归先失败再通过，真实生产执行复测通过。
7. Nginx 显式透传上游 `X-Accel-Buffering`，经代理的 SSE 头、增量、done、审计与 422 验收通过。

## 验证与追溯

本地最终全量：Backend604、Runner60、Frontend172、UI规则4，另类型/UI/content/dataset/refs检查通过。发布模拟6项在本地和服务器通过；独立审查未发现重要遗留问题。

服务器证据：`/root/learnda-release.log`、`/root/learnda-contracts.log`、`/root/learnda-final-health.log`。项目冷备份位于 `/var/backups/learn_da/`；验收库归档为 `20261031T160151Z-post-acceptance/acceptance-data.tar.gz`，未连接到线上应用。密钥仅保存在未跟踪、权限600的 `deploy/app.env` 与 `deploy/runner.env`，不记录到本文。

运行镜像 ID：

| 镜像 | ID |
| --- | --- |
| Backend | `sha256:6be696a0a20b0fe041b245ead2484fa94dfa504e8af3d4f2e9b95431d45bfc69` |
| Runner | `sha256:40167190f7d6c424e9237aea8c74bf4620031eb9ba8d0c860914da0b1de9eded` |
| Web | `sha256:8491cb3655b74f8347dccc5a74c6cb8fde80cd88a44783671103a2ba700f7c42` |
| Sandbox | `sha256:dcb1d0abe45deaab409ec3275174f3c5904c5914d2ca5ce2718e93790da4a202` |
