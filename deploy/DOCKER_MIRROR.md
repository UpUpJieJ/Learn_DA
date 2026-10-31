# Docker 镜像拉取与构建排查

当前默认基础镜像为 `python:3.12-slim`、`node:22-slim`、`nginx:1.27`。2026-11-01 的实际部署中，`nginx:1.27-slim` 经配置的镜像站返回 403，改用同版本 Debian 标签 `nginx:1.27` 后构建成功。不要再复制旧的 nginx slim 示例，也不要假设所有浮动标签都一直对应 Debian 12。

## 先区分失败来源

| 日志位置 | 对应来源 |
| --- | --- |
| load metadata、Pulling、manifest、HEAD 403 | Docker registry 或其镜像站；也可能是标签不存在/未同步 |
| apt-get update/install | Debian 软件源 |
| pip/uv install、wheel 下载 | PyPI 软件源 |
| npm ci | npm registry |

403 不能单独证明密码错误或项目代码有问题。先保留出错的 registry、tag 和完整错误，再定向重试；`--no-cache` 不能修复 manifest 403，反而增加下载和磁盘占用。

## 查看现状并拉取准确标签

以下在服务器 Bash 执行；`dc` 函数见[运维手册](README.md)。

```bash
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}'
docker info --format '{{json .RegistryConfig.Mirrors}}'
df -h /
docker pull python:3.12-slim
docker pull node:22-slim
docker pull nginx:1.27
```

拉取中断后可重试同一个标签，复用已完成层。先确认现有缓存和可用磁盘，保留其他项目仍在使用的镜像。

## 定向重建本项目

```bash
dc build web
# Python 基础镜像或后端构建问题时，分别查看对应服务
dc build backend
dc build runner
```

需要临时使用已核实的镜像来源或 digest 时，替换下面的示例值再构建：

```bash
NGINX_IMAGE='已核实的完整镜像名或digest'
dc build --build-arg "NGINX_BASE_IMAGE=$NGINX_IMAGE" web
```

Dockerfile 支持 PYTHON_BASE_IMAGE、NODE_BASE_IMAGE、NGINX_BASE_IMAGE，但当前 Compose 没有把这些名字自动映射为 build args。只在 app.env 写同名变量不会传入构建；要显式使用 `--build-arg`。长期调整应修改相应 Dockerfile 默认值并提交，避免下一次发布悄悄恢复原值。

只构建不会更新运行容器，部署与验收仍按运维手册执行。沙箱 tag 重建后还需重启 Runner，使进程重新解析 image ID。

## 镜像站与软件源配置

本机配置了多个 registry mirror。调整 `/etc/docker/daemon.json` 或重启 Docker daemon 会影响整台服务器上的其他项目，不属于 Learn DA 的常规更新步骤；需要整机维护安排后才操作。不要为本项目拉取失败直接执行全局 prune 或重启所有容器。

APT_MIRROR、PIP_INDEX_URL、PIP_TRUSTED_HOST、NPM_REGISTRY 的构建入口在两份 Compose 和 env 模板中。先确认失败属于对应软件源，再修改并只重建相关服务。换源不能代替依赖锁或课程回归验证。
