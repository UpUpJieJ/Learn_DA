#!/usr/bin/env bash
# Learn DA 本地一键部署脚本（Git Bash / Linux）
#
# 用法：
#   ./deploy/push-deploy.sh
#
# 行为：
#   1. 尽力推送 GitHub（直连失败自动走本地代理 127.0.0.1:7897）
#   2. 全量 bundle 上传服务器（GitHub 不可达时的更新数据源）
#   3. ssh 执行服务器端 update.sh（需已配置免密登录）
#
# 前置：deploy/update.sh 已在服务器；ssh root@SERVER 免密可用。

set -euo pipefail
cd "$(dirname "$0")/.."

SERVER="${LEARN_DA_SERVER:-43.142.89.100}"

echo "==> [1/3] 推送 GitHub（best-effort）"
if GIT_TERMINAL_PROMPT=0 git push origin main 2>/dev/null \
   || git -c http.proxy=http://127.0.0.1:7897 push origin main 2>/dev/null; then
    echo "    GitHub 已同步"
else
    echo "    GitHub 不可达，跳过（服务器将使用 bundle 更新）"
fi

echo "==> [2/3] 上传 bundle 到服务器"
BUNDLE=$(mktemp /tmp/learnda.XXXXXX.bundle)
trap 'rm -f "$BUNDLE"' EXIT
git bundle create "$BUNDLE" main
scp -q "$BUNDLE" root@"$SERVER":/root/learnda.bundle
echo "    bundle 已上传"

echo "==> [3/3] 执行服务器更新"
ssh root@"$SERVER" /app/Learn_DA/deploy/update.sh
