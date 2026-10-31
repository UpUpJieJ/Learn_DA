# Learn DA 生产部署

生产部署使用两台 Linux 服务器：应用服务器运行 Web 与 Backend，Runner
服务器只运行受限代码执行服务。Runner 的 Docker socket 只存在于专用
Runner 主机，应用服务器不得挂载该 socket。

## 1. 准备条件

- 两台服务器均安装 Docker Engine 和 Docker Compose v2。
- Runner 私网地址可被应用服务器访问；公网和其他主机不得访问其 8080 端口。
- 两台服务器均获取同一版本的仓库代码。
- 生产使用 HTTPS 时，在应用服务器的 80 端口前部署现有负载均衡器、Caddy
  或 Nginx 做 TLS 终止。

## 2. 部署 Runner 服务器

在 Runner 主机的仓库根目录执行：

```bash
cp deploy/runner.env.example deploy/runner.env
sudo stat -c '%g' /var/run/docker.sock
openssl rand -hex 32
```

编辑 `deploy/runner.env`：

- 设置 `RUNNER_BIND_ADDRESS` 为该主机的私网 IP；
- 把 `DOCKER_SOCKET_GID` 设置为上一步输出的数字；
- 把 `RUNNER_TOKEN` 设置为生成的随机值，并安全保存，稍后复制到应用服务器；
- 不要把 `8080` 绑定到 `0.0.0.0`，也不要把 Runner 暴露到公网。

构建并启动 Runner 与沙箱镜像：

```bash
docker compose --env-file deploy/runner.env -f docker-compose.runner.yml \
  --profile sandbox build
docker compose --env-file deploy/runner.env -f docker-compose.runner.yml \
  up -d --build runner
docker compose --env-file deploy/runner.env -f docker-compose.runner.yml ps
```

`runner` 状态应为 `healthy`。从应用服务器可执行：

```bash
curl -fsS http://RUNNER_PRIVATE_IP:8080/ready
```

这个端点只表示 Docker 执行提供者可用；执行接口仍要求 `X-Runner-Token`。

## 3. 部署应用服务器

在应用服务器的仓库根目录执行：

```bash
cp deploy/app.env.example deploy/app.env
openssl rand -hex 32
```

编辑 `deploy/app.env`：

- 设置 `PUBLIC_ORIGIN` 为实际 `https://` 域名；
- 设置 `RUNNER_URL=http://RUNNER_PRIVATE_IP:8080`；
- 把 Runner 的 `RUNNER_TOKEN` 原样复制过来；
- 将新生成的另一随机值设置为 `SESSION_SECRET`；
- 填写 LLM 配置；
- 单个 Backend 可保留 SQLite。多个副本或高并发写入时改为 MySQL 的异步连接串。

启动应用：

```bash
docker compose --env-file deploy/app.env -f docker-compose.app.yml build backend migrate web
docker compose --env-file deploy/app.env -f docker-compose.app.yml up -d
docker compose --env-file deploy/app.env -f docker-compose.app.yml ps
```

Backend 完成迁移并通过 `/ready` 后，Web 才会启动。浏览器访问
`PUBLIC_ORIGIN` 验证页面。

## 4. 验收与日常操作

在应用服务器查看服务健康状态：

```bash
docker compose --env-file deploy/app.env -f docker-compose.app.yml ps
docker compose --env-file deploy/app.env -f docker-compose.app.yml logs --tail=100 backend
```

在 Runner 服务器查看执行服务：

```bash
docker compose --env-file deploy/runner.env -f docker-compose.runner.yml ps
docker compose --env-file deploy/runner.env -f docker-compose.runner.yml logs --tail=100 runner
```

发布新版本时，先更新并重建 Runner，再运行 Alembic 并更新应用服务器。部署后运行
`bash deploy/acceptance.sh`，验证工作区真实执行、幂等、进度/报告、分级提示与 SSE。
正式判定使用 observations 协议，后端与 Runner 必须配套更新。不要把
`deploy/app.env` 或 `deploy/runner.env` 提交到 Git。

后端镜像从 `learn_da/uv.lock` 冻结导出生产依赖并校验哈希；Runner 从
`learn_da_runner/requirements.lock` 安装，避免全新构建暗中升级依赖。
Runner 升级依赖时用 `uv pip compile learn_da_runner/pyproject.toml --universal
--python-version 3.12 --generate-hashes --no-header --no-annotate -o
learn_da_runner/requirements.lock` 更新锁，再在相同依赖环境跑测试及 Docker 验收。

## 单台服务器部署

推荐使用两台服务器。只有一台服务器时，Runner 仍会持有宿主 Docker
socket，不能获得物理主机级隔离；但可将其端口限制在 `127.0.0.1`，并让
Backend 仅通过 Docker 内部网络访问它。

在同一台服务器完成前两节的环境变量准备后，修改：

- `deploy/app.env`：设置 `RUNNER_URL=http://runner:8080`；
- `deploy/runner.env`：设置 `RUNNER_BIND_ADDRESS=127.0.0.1`；
- 两个文件的 `RUNNER_TOKEN` 必须完全相同。

使用同一个 Compose 项目启动全部服务：

```bash
docker compose --env-file deploy/app.env --env-file deploy/runner.env \
  -f docker-compose.app.yml -f docker-compose.runner.yml --profile sandbox build
docker compose --env-file deploy/app.env --env-file deploy/runner.env \
  -f docker-compose.app.yml -f docker-compose.runner.yml up -d --build
docker compose --env-file deploy/app.env --env-file deploy/runner.env \
  -f docker-compose.app.yml -f docker-compose.runner.yml ps
```

同一次启动会使 `backend` 与 `runner` 处于同一个内部 Docker 网络，因此
`http://runner:8080` 不需要公网 DNS 或端口映射。

## 日常更新（仓库有新提交后同步到服务器）

服务器端一条命令：

```bash
/app/Learn_DA/deploy/update.sh
```

脚本会拉取代码（优先 GitHub，不可达时回退 `/root/learnda.bundle`），
按内容缓存构建版本化沙箱镜像，再顺序构建应用镜像。停止写入后冷备份本项目
数据和日志卷，依次等待 Runner、迁移、Backend、Web 就绪，最后运行 29 项验收。
默认保留数据。备份保存在服务器 `/var/backups/learn_da/`，权限为 700。

单机双 compose 下，后端请求超时在 `app.env` 使用
`BACKEND_RUNNER_TIMEOUT_SECONDS=7` 和 `BACKEND_RUNNER_SESSION_TIMEOUT_SECONDS=30`；
Runner 仍用 `RUNNER_TIMEOUT_SECONDS=5` 和 `RUNNER_SESSION_TIMEOUT_SECONDS=20`。
分开配置可避免后加载的 `runner.env` 把后端超时一起改短。

### 本地侧：把新提交送到服务器

先提交全部发布文件（含新迁移、参考结果和 Runner 子进程文件），再指定已确认的 SSH 别名：

```bash
LEARN_DA_SERVER=<SSH别名> bash deploy/push-deploy.sh
```

脚本拒绝脏工作区；尽力推 GitHub，并始终上传完整 main bundle，部署时核验确切
commit。服务器执行新上传的更新脚本，避免旧脚本遗漏沙箱构建。首次安装需先在目标
`/app/Learn_DA` 克隆 bundle、设置 origin，并准备两个未跟踪的 env 文件。

用户明确要求清空历史时使用：

```bash
LEARN_DA_SERVER=<SSH别名> bash deploy/push-deploy.sh --fresh
```

`--fresh` 在冷备份成功后删除这一个 compose 项目的数据/日志卷，再迁移空库。
删除前核验卷的 project 和 logical-volume 标签；不会使用全局 prune 或删除其他
项目容器。验收会写入专用匿名访客数据；需要完全空库交付时，验收后再停写并重建数据库。
通过 `LEARN_DA_COMPOSE_PROJECT` 可选择已有项目名，默认 `learn_da`。
发布脚本回归可运行 `bash deploy/test-release.sh`（隔离模拟，无 Docker/网络调用）。

### 免密登录（可选，一次性配置）

```bash
ssh-keygen -t ed25519            # 本地无密钥时生成
ssh root@<服务器IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys" < ~/.ssh/id_ed25519.pub
```

配置后本地 scp/ssh 不再需要输密码，方式 A/B 可写成单条脚本自动执行。
