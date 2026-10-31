# Learn DA 部署与运维手册

更新于 2026-11-01。适用于当前 `lavm` 上的单机双 Compose 部署，供日常更新、故障排查和备份恢复使用。本次上线的版本、镜像 ID 与验收证据见[全新部署记录](../learn_da/docs/deployment-2026-11-01.md)。普通更新保留学习数据；11 月 1 日的清空历史是一次性操作。

## 当前环境

| 项目 | 当前约定 |
| --- | --- |
| SSH | `ssh lavm`，别名和地址在本机 `~/.ssh/config`；不把 IP、密码或私钥写入仓库 |
| 服务器目录 | `/app/Learn_DA` |
| Compose 项目名 | `learn_da`，所有运维命令显式指定 |
| 编排 | 同时加载 `docker-compose.app.yml` 与 `docker-compose.runner.yml` |
| 访问入口 | Nginx Web，宿主 80 端口；实际地址见 `deploy/app.env` 的 `PUBLIC_ORIGIN` |
| Backend | 内网 8000，不映射到宿主；负责可信判定和学习状态 |
| Runner | 宿主仅 `127.0.0.1:8080`；Backend 访问 `http://runner:8080` |
| 学习数据库 | SQLite，容器 `/app/data/learn_da.db` |
| 数据卷 | `learn_da_learn_da_data`；逻辑卷名 `learn_da_data` |
| 日志卷 | `learn_da_learn_da_logs`；逻辑卷名 `learn_da_logs` |
| Runner 临时目录 | 宿主与 Runner 内均为 `/var/lib/learn_da/runner-work`，700，65532:0 |
| 配置密钥 | 服务器 `deploy/app.env`、`deploy/runner.env`，600，Git 忽略 |
| Hermes | root 的用户级 `hermes-gateway.service`；当前已停止，但仍为 enabled |
| 其他业务 | 同机其他项目不属于本项目的更新、停止或清理范围 |

当前 Runner 持有宿主 Docker socket。沙箱容器隔离不等同于专用物理主机隔离。未来拆到两台机器时，应用端只加载 app 编排，Runner 端只加载 runner 编排；改用可达的私网地址和相同 token，应用服务器不挂 Docker socket。下面的一键更新脚本只适用于当前单机 SQLite 部署。

## 服务器命令入口

以下标注为服务器的命令，在 `ssh lavm` 后的 Bash 中运行。每个新会话先定义：

```bash
cd /app/Learn_DA
dc() {
  docker compose --project-name learn_da \
    --env-file deploy/app.env --env-file deploy/runner.env \
    -f docker-compose.app.yml -f docker-compose.runner.yml "$@"
}
```

`dc` 是当前 shell 的函数，不会跨 SSH 会话自动保留。保持项目名、目录和两份编排一致，避免启动第二套服务或误用空数据卷。

## 日常更新

### 本地准备

在本地仓库检查 `git status`、当前分支和差异，提交本次全部文件，包括新迁移、refs、锁文件与 Runner 子进程文件。发布脚本只接受干净的 `main`，不会发送未跟踪或未提交的代码。

CI 账单限制解除前，业务代码提交前按 [AGENTS.md](../AGENTS.md) 跑全量门禁：后端 pytest、内容/数据集/refs 校验、Runner pytest、前端 vitest/type-check/UI lint，以及发布脚本回归。Windows 本机 esbuild 临时文件删除可能被环境拦截；实际生产构建由服务器 Docker 完成。

```bash
# 本地 Git Bash，仓库根目录；也可在 Linux Bash 使用
git status --short
git branch --show-current
bash deploy/test-release.sh

# 完成测试与提交后再发布
LEARN_DA_SERVER=lavm bash deploy/push-deploy.sh
```

本机 Git Bash 位于 `F:/Git/Git/bin/bash.exe`。从 PowerShell 调用：

```powershell
$env:LEARN_DA_SERVER = 'lavm'
& 'F:/Git/Git/bin/bash.exe' deploy/push-deploy.sh
```

`LEARN_DA_SERVER` 指定 SSH 别名，不再使用旧脚本中的默认 IP。遇到 SSH 主机指纹变化时，先核实服务器身份，不关闭主机密钥检查。

### 脚本实际执行的流程

1. 尽力推送 GitHub，直连失败尝试本机 7897 代理。
2. 始终上传完整 main bundle 到 `/root/learnda.bundle`，并上传新版 updater 到 `/root/learnda-update.sh`。
3. 服务器从 bundle 核对并快进到指定 commit；脏目录、版本不符或分叉均中止。
4. 利用 Docker 内容缓存构建沙箱，顺序构建 Backend、migrate、Runner、Web。
5. 停止 Web/Backend 写入后冷备份项目数据和日志卷。
6. 初始化共享运行目录，等待 Runner 就绪，执行迁移，再启动 Backend/Web。
7. 通过实际 HTTP 入口运行 29 项验收，最后显示容器状态。

构建阶段通常仍由旧容器服务；停止写入到重新启动期间存在维护中断。脚本失败会停止后续步骤，**没有自动回滚**，应按失败阶段处理。不要在失败后直接清库。

仅在服务器已有最新 updater、代码来源已同步时，可执行：

```bash
# 服务器 Bash
cd /app/Learn_DA
set -o pipefail
bash deploy/update.sh 2>&1 | tee "/root/learnda-update-$(date -u +%Y%m%dT%H%M%SZ).log"
```

服务器直接更新优先拉 GitHub，不可达时使用已有 bundle；旧 bundle 不会凭空包含新提交。首次更新部署脚本本身时，优先使用本地 `push-deploy.sh`，确保执行的是新版 updater。脚本文件按 Bash 调用，不依赖可执行权限。

### 只更新沙箱时需要重启 Runner

Runner 进程首次使用沙箱 tag 后固定其 image ID。当前 updater 的 `up -d runner` 不保证重建一个镜像和配置都没变化的 Runner 容器；因此只改沙箱镜像时，需要手动补充重建 Runner，再验收。否则可能仍在测旧沙箱。

```bash
# 服务器 Bash，镜像构建完成后，在维护窗口执行
dc up -d --no-deps --force-recreate --wait --wait-timeout 120 runner
docker exec learn_da-backend-1 python scripts/verify_observation_runner.py \
  --runner-url http://runner:8080
LEARN_DA_BASE_URL=http://127.0.0.1 bash deploy/acceptance.sh
```

若配置了非 80 的 HTTP_PORT，相应修改验收 URL。依赖升级还需同步后端约束、沙箱 Dockerfile、版本 tag、锁文件与生成 refs，并重新验证全部课程。

## 配置注意点

| 配置 | 当前要求 |
| --- | --- |
| `PUBLIC_ORIGIN` | 与浏览器实际访问的 origin 一致；访问地址以服务器 env 为准 |
| `PUBLIC_SCHEME` | 当前为 http；切 HTTPS 时改 https，影响 cookie Secure 属性 |
| `RUNNER_URL` | 单机使用 `http://runner:8080`，不能用 Backend 容器自己的 localhost |
| `RUNNER_TOKEN` | 两份 env 必须一致；更改后配套重建 Backend/Runner |
| `SESSION_SECRET` | 至少 32 字符，保持稳定；更换会使旧匿名 session cookie 失效 |
| `DOCKER_SOCKET_GID` | 在目标服务器用 `stat -c '%g' /var/run/docker.sock` 获取；本次为 123，不是通用常量 |
| Backend 执行超时 | app.env 用 `BACKEND_RUNNER_TIMEOUT_SECONDS=7`、`BACKEND_RUNNER_SESSION_TIMEOUT_SECONDS=30` |
| Runner 执行超时 | runner.env 用 `RUNNER_TIMEOUT_SECONDS=5`、`RUNNER_SESSION_TIMEOUT_SECONDS=20` |
| LLM 超时 | idle 60 秒、单次流式总预算 180 秒；后者包含重试和退避 |
| 生产执行后端 | Docker；不能用 local 代替生产沙箱 |
| 启用模块 | 必须包含 learning/playground/agent/analytics/learner_state/workspace |
| 数据库 | updater 当前仅接受项目 /app/data 内的标准 SQLite URL；不能直接用于 MySQL 发布 |

双 `--env-file` 后加载的同名变量会覆盖前者，后端与 Runner 的预算因此使用不同配置名。只编辑 env 文件不会改变现有容器环境，需要重建相关服务。

后端从 `learn_da/uv.lock` 冻结导出生产依赖并校验哈希；Runner 使用 `learn_da_runner/requirements.lock`；前端使用 `package-lock.json` 与 `npm ci`。不要用无锁安装结果替代已验证的生产依赖。

共享工作目录必须在宿主和 Runner 内保持同一绝对路径，启动前由 root 执行：

```bash
install -d -m 700 -o 65532 -g 0 /var/lib/learn_da/runner-work
stat -c '%a %u:%g %n' /var/lib/learn_da/runner-work
```

Compose 的 `create_host_path:false` 和 Runner 构造校验用于阻止错误目录配置。沙箱只读挂载单次请求的子目录，执行后自动删除；不要把整个共享根目录挂到沙箱。迁移目录时必须同时修改 compose 的 source/target、RUNNER_WORK_ROOT 和初始化步骤。

不要打印完整 `docker compose config`、容器环境或 env 文件到公共日志/聊天；需要校验编排时用 `dc config --quiet`。配置文件不入 Git，保留服务器上的 600 权限。

## 更新后的验证

### 健康与访问检查

```bash
dc ps
dc exec -T backend curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8080/ready
curl -fsS http://127.0.0.1/api/v1/lessons \
  | python3 -c 'import json,sys; print("lessons =",len(json.load(sys.stdin)["data"]))'
dc exec -T backend alembic current
```

Backend、Runner 应为 healthy，Web 为 Up；migrate 成功退出是正常状态。当前共 13 门课，迁移 head 为 `d8a42b6f9013`，后续以仓库实际 head 为准。Web 没有单独配置健康检查，`--wait` 对它只确认运行，仍需 HTTP 检查。

不要用 Web 的 `/ready` 检查后端，它可能返回 SPA HTML。Backend 的 ready 只检查数据库连通与 Runner/Docker 可用，不能证明 driver、课程判定和 LLM 都正常。

### 全课程执行检查

```bash
dc exec -T backend python scripts/verify_observation_runner.py \
  --runner-url http://runner:8080
```

当前应为 **76/76**：13 课 38 个任务的起步代码必须失败、参考解必须通过。该脚本只创建短命沙箱，不写学习数据库，适合排查执行/依赖/refs 问题。

### 完整生产验收

```bash
LEARN_DA_BASE_URL=http://127.0.0.1 bash deploy/acceptance.sh
```

当前应为 **29/29**，覆盖真实执行、幂等、进度/报告、失效、提示、真实 LLM 和 SSE。它会创建匿名验收访客并写入学习、任务和 Agent 记录。日常更新默认保留这些记录；**不要为了保持空库而清除真实用户数据**。

本次空库交付的 14 张业务表 0 行，是 2026-11-01 的初始快照，开始使用后出现记录属于正常情况。检查进度、幂等和访客隔离时，使用保留 cookie 的真实浏览器或 curl cookie jar；IAB 不持久化 cookie，可能把每次请求都当作新访客。

## 备份与恢复

### 发布时的自动备份

updater 在停止 Web/Backend 后，使用新构建的 Backend 镜像冷备份两个自有卷，目录形式为：

```text
/var/backups/learn_da/<UTC时间Z>-<目标commit前12位>/
  previous-revision.txt
  learn_da_data.tar.gz
  learn_da_logs.tar.gz
```

目录权限 700；卷不存在时不会生成对应归档，只有 previous-revision.txt 不代表有数据库备份。备份失败时脚本不进入删除卷步骤。备份目录按 UTC 命名，比新加坡时间早 8 小时。

发布脚本触发的备份不等于定时备份；当前脚本不包含定时任务，也不备份 env/私钥。密钥应另行安全保管。previous-revision.txt 是更新前的 Git checkout，可能含文档提交，不能单凭它判断此前运行的镜像版本。

```bash
find /var/backups/learn_da -maxdepth 2 -type f
# 选择真实存在的目录后检查归档
BACKUP_DIR='/var/backups/learn_da/选中的备份目录'
tar -tzf "$BACKUP_DIR/learn_da_data.tar.gz"
```

### 恢复 SQLite

先确认备份来源、时间以及与应用/迁移版本的兼容性。恢复会替换当前学习库，应在维护窗口执行，并保留被替换库的快照。下面只恢复该项目数据卷内的 SQLite 文件，不恢复其他项目或日志卷。

```bash
# 服务器 Bash，先定义 dc；填写并确认备份路径
BACKUP_DIR='/var/backups/learn_da/选中的备份目录'
test -f "$BACKUP_DIR/learn_da_data.tar.gz" || exit 1
test "$(docker volume inspect learn_da_learn_da_data --format '{{index .Labels "com.docker.compose.project"}}')" = learn_da || exit 1
test "$(docker volume inspect learn_da_learn_da_data --format '{{index .Labels "com.docker.compose.volume"}}')" = learn_da_data || exit 1

dc stop web backend
RECOVERY_DIR="/var/backups/learn_da/$(date -u +%Y%m%dT%H%M%SZ)-before-restore"
install -d -m 700 "$RECOVERY_DIR"
docker run --rm -i --network none --user 0 --entrypoint python \
  --mount type=volume,source=learn_da_learn_da_data,target=/data \
  --mount "type=bind,source=$BACKUP_DIR,target=/restore,readonly" \
  --mount "type=bind,source=$RECOVERY_DIR,target=/safety" \
  learn_da-backend - <<'PY'
import os, pwd, shutil, tarfile
from pathlib import Path, PurePosixPath
root = Path("/data")
allowed = {"learn_da.db", "learn_da.db-wal", "learn_da.db-shm"}
with tarfile.open("/restore/learn_da_data.tar.gz", "r:gz") as source:
    files = {}
    for member in source.getmembers():
        parts = PurePosixPath(member.name).parts
        if member.isdir() and not parts:
            continue
        assert member.isfile() and len(parts) == 1 and parts[0] in allowed, member.name
        files[parts[0]] = member
    assert "learn_da.db" in files
    with tarfile.open("/safety/current-data.tar.gz", "w:gz") as safety:
        safety.add(root, arcname=".")
    for name in allowed:
        (root / name).unlink(missing_ok=True)
    user = pwd.getpwnam("appuser")
    for name, member in files.items():
        with source.extractfile(member) as incoming, (root / name).open("wb") as output:
            shutil.copyfileobj(incoming, output)
        os.chown(root / name, user.pw_uid, user.pw_gid)
        (root / name).chmod(0o600)
print("SQLite restored; previous data saved in /safety/current-data.tar.gz")
PY

# 只有在确认目标代码可升级这份备份后执行
dc run --rm -T --interactive=false --no-deps migrate
dc up -d --no-deps --wait --wait-timeout 180 backend
dc up -d --no-deps --wait --wait-timeout 60 web
dc exec -T backend alembic current
```

发生恢复错误时保持停止写入，检查恢复日志与 `RECOVERY_DIR`，不要继续覆盖备份。回退到旧应用时，先确认其支持当前 schema；未经验证不要直接运行 Alembic downgrade。当前脚本没有自动匹配旧代码、旧镜像与旧数据库的回滚功能。

### 明确要求清空历史时

只有新的清空授权或确认可丢弃的测试环境才使用：

```bash
# 本地 Git Bash；会替换项目数据与日志卷
LEARN_DA_SERVER=lavm bash deploy/push-deploy.sh --fresh
```

`--fresh` 在自有卷冷备份成功后停止本项目容器、核对卷标签、移除两个自有卷，再迁移新库；它仍会在最后写入验收数据。完全空库交付需要在验收完成后另行停写、备份并重建学习库，不能把这个步骤用于已有真实用户的普通更新。

本次验收数据另存为 `/var/backups/learn_da/20261031T160151Z-post-acceptance/acceptance-data.tar.gz`。这是验收库归档，不是要恢复到线上继续使用的用户历史。

## 排查顺序与常见问题

先收集状态、失败阶段和日志，不立即删除数据或重建所有容器：

```bash
dc ps -a
dc logs --tail=150 backend runner web
dc logs --tail=150 migrate
docker stats --no-stream
free -h
df -h /
docker system df
```

本次部署留下的 `/root/learnda-release.log`、`learnda-contracts.log`、`learnda-final-health.log` 是这次人工保存的证据；以后更新使用新的带时间日志，不能把旧的 29/29 当成本次结果。

| 现象 | 优先检查与处理 |
| --- | --- |
| SSH 指纹变化或连错机器 | 核对本机 SSH config 与目标身份；旧脚本的默认 IP 已废弃 |
| dirty checkout、bundle/revision mismatch、ff-only 失败 | 检查本地/服务器 git status 和实际提交；提交或妥善保存差异后重发 bundle，不用 reset --hard 覆盖现场 |
| 镜像 403、超时、npm/pip 下载失败 | 区分失败的 registry/tag 与软件源，见[镜像排查](DOCKER_MIRROR.md)；保留缓存，先定向重试 |
| 构建失败在第 1/2 阶段 | 通常尚未停止旧容器；确认 dc ps。修复后重试，先不要清库 |
| 备份阶段失败后 Web/Backend 停止 | 先修复备份路径/磁盘/卷归属；若迁移尚未开始且旧容器仍在，可用 dc start backend web 恢复原容器，不用 up 换成未验收的新镜像 |
| /work/driver.py 不存在 | 核对共享目录 source/target/配置路径是否相同，不能用 Runner 私有 /tmp；仅有 ready=200 不能排除此故障 |
| Runner 无法连接 Docker、permission denied | 检查 socket GID、group_add、目录 700 与属主 65532:0；不以 chmod 777 或开启 local 绕过 |
| 更新沙箱后表现仍像旧版本 | Runner 固定了旧 image ID；force-recreate Runner 后重跑 76 项 |
| migration 失败或字段缺失 | 查看 migrate 日志、当前版本和 head；不要跳过迁移直接启动新版 Backend |
| 页面 502、执行服务不可用 | 先看 Backend/Runner 是否健康、内部 runner:8080 是否可达、服务 token 和超时是否配套 |
| 会话不存在、刷新进度丢失 | 检查 PUBLIC_SCHEME、cookie、同源代理；身份测试不要使用每请求新访客的 IAB |
| workspace 全 404 | 检查 ENABLED_APP_MODULES 是否包含 workspace，以及是否启动了正确镜像 |
| SSE 头缺失或一次性吐完 | 检查实际使用的 learn_da_vue/nginx.conf、上游 X-Accel-Buffering:no 与 proxy_pass_header；通过 Web 入口复测 |
| AI 助手不可用但判题正常 | 查看 LLM 配置存在性、模型权限/额度/网络和 Backend 的 fallback_reason/LLM 日志；没有备用 key 自动切换 |
| 新版验收失败 | 先保存原始失败和日志；必要时 dc stop web 保留维护窗口，修复后重试，不能把 readiness 当功能验收 |

资源不足时先检查本项目构建和备份占用。2026-11-01 实测该主机约 1.9 GiB RAM、2 GiB swap，发布后约 1.1 GiB 可用内存、3.7 GiB 可用磁盘；这些是快照，更新前重新检查。不要执行全局容器/卷 prune 或重启整个 Docker daemon，影响同机其他项目；旧镜像和备份需核对归属后定向清理。

## Hermes 的启停

必须以 root 登录后操作用户级 systemd，不能把它当作系统级服务：

```bash
systemctl --user show hermes-gateway.service -p ActiveState -p MainPID -p UnitFileState
systemctl --user status hermes-gateway.service --no-pager
journalctl --user -u hermes-gateway.service -n 80 --no-pager

# 暂停；本次已执行
systemctl --user stop hermes-gateway.service

# 需要恢复时先检查 free -h，再启动
systemctl --user start hermes-gateway.service
```

当前为 `inactive`、`MainPID=0`、`UnitFileState=enabled`：本次仅停止，重启服务器后仍可能自动启动。若明确要求跨重启保持关闭，再执行 `systemctl --user disable --now hermes-gateway.service`；需要恢复开机启动时用 `enable --now`。普通项目更新不自动启停 Hermes 或其他业务。

## 首次安装与迁移到新服务器

首次安装不是直接调用更新脚本：先确认 SSH 身份，安装 Docker/Compose v2、Git、python3、curl、tar，获取 main 代码到 `/app/Learn_DA`，设置 origin，再复制两个 env 模板并填入真实配置。单机模式特别设置 RUNNER_URL=http://runner:8080、RUNNER_BIND_ADDRESS=127.0.0.1、相同 token 和目标 socket GID，env 权限为 600。

```bash
# 新服务器已克隆代码并填写 env 后
cd /app/Learn_DA
chmod 600 deploy/app.env deploy/runner.env
install -d -m 700 -o 65532 -g 0 /var/lib/learn_da/runner-work
# 使用本手册定义的 dc 函数
dc config --quiet
# updater 会补建沙箱、迁移、启动并验收；不额外加 --fresh
bash deploy/update.sh
```

本地 GitHub 不可达时可先 `git bundle create release.bundle main`，上传到服务器再 `git clone -b main /root/learnda.bundle /app/Learn_DA`，随后把 origin 设置为项目 GitHub URL。env 密钥独立安全迁移；不把真实配置加到 Git bundle。

Windows Git Bash 传远端绝对路径时留意 MSYS 参数转换，需要时设置 `MSYS_NO_PATHCONV=1`。通过 SSH 执行多行脚本时，先上传脚本文件再用 Bash 执行；不要把脚本源码经 stdin 直接喂给会读取 stdin 的 docker compose run，否则后续脚本可能被吞掉。一次性 migrate 命令可用 `run --rm -T --interactive=false --no-deps migrate`；`-T` 只关闭伪终端，`--interactive=false` 才关闭 stdin。

每次更新后，在[部署记录目录](../learn_da/docs/)补充应用 commit、镜像 ID、迁移 head、验收命令/结果、备份位置和实际故障处理。Git HEAD 只表示 checkout 版本，拉代码并不会更新已运行镜像；文档提交也不要求重建应用。
