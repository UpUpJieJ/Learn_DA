#!/usr/bin/env bash
# Run from Git Bash/Linux. LEARN_DA_SERVER must be an SSH alias or user@host.
set -euo pipefail
cd "$(dirname "$0")/.."

SERVER="${LEARN_DA_SERVER:?Set LEARN_DA_SERVER to the confirmed SSH alias}"
[[ "$SERVER" =~ ^[a-zA-Z0-9_.@:-]+$ && "$SERVER" != -* ]] || { echo "Invalid SSH target" >&2; exit 2; }
[[ $# -eq 0 || ( $# -eq 1 && "$1" == --fresh ) ]] || { echo "Usage: $0 [--fresh]" >&2; exit 2; }
[[ "$(git branch --show-current)" == main ]] || { echo "Release main only" >&2; exit 2; }
[[ -z "$(git status --porcelain)" ]] || { echo "Commit all release files before deployment" >&2; exit 2; }
REVISION=$(git rev-parse HEAD)

echo "==> [1/3] Push GitHub (bundle remains the authoritative release source)"
if GIT_TERMINAL_PROMPT=0 git push origin main \
   || GIT_TERMINAL_PROMPT=0 git -c http.proxy=http://127.0.0.1:7897 push origin main; then
    echo "GitHub synchronized"
else
    echo "GitHub unavailable; continuing with the exact-commit bundle"
fi

echo "==> [2/3] Upload release $REVISION"
BUNDLE=$(mktemp)
trap 'rm -f "$BUNDLE"' EXIT
git bundle create "$BUNDLE" main
scp -q "$BUNDLE" "$SERVER":/root/learnda.bundle
# Bootstrap with the NEW update script, even when the server has the old one.
scp -q deploy/update.sh "$SERVER":/root/learnda-update.sh

echo "==> [3/3] Deploy the uploaded revision"
ssh "$SERVER" "bash /root/learnda-update.sh --revision $REVISION ${1:-}"
