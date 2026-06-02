# Docker 拉取镜像 403 / 超时排查

## 现象

```
failed to resolve source metadata for docker.io/library/python:3.12-bookworm-slim
unexpected status from HEAD request to https://docker.m.daocloud.io/...: 403 Forbidden
```

说明本机 Docker 配置了 **DaoCloud 等 registry-mirror**，但该镜像站对 `library/python` 部分标签返回 403 或未同步。

## 方案一：改用通用 `-slim` 标签（项目默认）

本项目已使用 `python:3.12-slim`、`node:22-slim`、`nginx:1.27-slim`（均为 Debian bookworm 系），比 `*-bookworm-slim` 更容易被镜像站缓存。

重新构建：

```bash
docker compose -f docker-compose.prod.yml build --no-cache
```

## 方案二：构建时传入基础镜像（勿在 .env 里留空变量）

```bash
docker compose -f docker-compose.prod.yml build \
  --build-arg PYTHON_BASE_IMAGE=docker.1ms.run/library/python:3.12-slim

cd learn_da_vue && docker build \
  --build-arg NODE_BASE_IMAGE=docker.1ms.run/library/node:22-slim \
  --build-arg NGINX_BASE_IMAGE=docker.1ms.run/library/nginx:1.27-slim \
  -t learn_da_web .
```

注意：不要在 `deploy/.env` 中写 `NGINX_BASE_IMAGE=` 空值，否则会覆盖 Dockerfile 默认值导致构建失败。

## 方案三：修改 / 移除有问题的 registry-mirror

编辑 `/etc/docker/daemon.json`（示例，勿同时堆太多失效镜像）：

```json
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
```

若 DaoCloud 持续 403，请**删除** `https://docker.m.daocloud.io` 后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

## 方案四：先手动拉取再构建

```bash
docker pull python:3.12-slim
docker pull node:22-slim
docker pull nginx:1.27-slim
docker compose -f docker-compose.prod.yml build
```
