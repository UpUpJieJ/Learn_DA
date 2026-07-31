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
docker compose --env-file deploy/app.env -f docker-compose.app.yml up -d --build
docker compose --env-file deploy/app.env -f docker-compose.app.yml ps
```

需要 Redis 时，在两条命令增加 `--profile redis`。Backend 完成迁移并通过
`/ready` 后，Web 才会启动。浏览器访问 `PUBLIC_ORIGIN` 验证页面。

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

发布新版本时，先更新并重建 Runner，再更新应用服务器。部署后分别验证三节
样板课程的练习执行、验证结果、草稿恢复和 Dashboard 指标。不要把
`deploy/app.env` 或 `deploy/runner.env` 提交到 Git。

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
