#!/usr/bin/env bash
# Learn DA 云服务器更新脚本（在服务器上执行）
#
# 用法：
#   /app/Learn_DA/deploy/update.sh
#
# 代码来源优先级：
#   1. GitHub origin/main（网络通畅时）
#   2. /root/learnda.bundle（GitHub 不可达时，由本地推送上传）
#
# 行为：
#   - 拉取最新代码（快进合并，不做三方合并）
#   - 重建 backend / migrate / web / runner 镜像（层缓存下未变更的秒级完成）
#   - Dockerfile.sandbox 或 learn_da/docker/ 变更时额外重建沙箱镜像
#   - up -d 滚动更新（migrate 先跑 Alembic，成功后 backend/web 才启动）
#   - 数据卷 learn_da_data 不受影响，历史数据保留

set -euo pipefail
cd "$(dirname "$0")/.."

ENV_ARGS=(--env-file deploy/app.env --env-file deploy/runner.env)
COMPOSE_FILES=(-f docker-compose.app.yml -f docker-compose.runner.yml)
BUNDLE=/root/learnda.bundle

echo "==> [1/4] 更新代码"
BEFORE=$(git rev-parse --short HEAD)
if GIT_TERMINAL_PROMPT=0 git -c http.version=HTTP/1.1 pull --ff-only origin main; then
    echo "    已从 GitHub 更新"
elif [ -f "$BUNDLE" ]; then
    git pull --ff-only "$BUNDLE" main
    echo "    已从 bundle 更新"
else
    echo "    更新失败：GitHub 不可达且 $BUNDLE 不存在" >&2
    exit 1
fi
AFTER=$(git rev-parse --short HEAD)
echo "    $BEFORE -> $AFTER"

echo "==> [2/4] 重建镜像"
CHANGED=$(git diff --name-only "HEAD@{1}" HEAD 2>/dev/null || true)
if echo "$CHANGED" | grep -qE '^learn_da/(Dockerfile\.sandbox|docker/)'; then
    echo "    检测到沙箱镜像变更，重建 sandbox-image"
    docker compose "${ENV_ARGS[@]}" "${COMPOSE_FILES[@]}" --profile sandbox build sandbox-image
fi
docker compose "${ENV_ARGS[@]}" "${COMPOSE_FILES[@]}" build backend migrate web runner

echo "==> [3/4] 滚动更新容器"
docker compose "${ENV_ARGS[@]}" "${COMPOSE_FILES[@]}" up -d

echo "==> [4/4] 容器状态"
docker compose "${ENV_ARGS[@]}" "${COMPOSE_FILES[@]}" ps
echo "完成：$BEFORE -> $AFTER"
