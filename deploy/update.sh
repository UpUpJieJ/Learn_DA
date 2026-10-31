#!/usr/bin/env bash
# Single-host release. Default: preserve data. --fresh: back up, then reset ONLY
# this Compose project's data/log volumes. Requires deploy/*.env on the server.
set -euo pipefail
REPO="${LEARN_DA_REPO:-/app/Learn_DA}"
PROJECT="${LEARN_DA_COMPOSE_PROJECT:-learn_da}"
BUNDLE="${LEARN_DA_BUNDLE:-/root/learnda.bundle}"
REVISION=""
FRESH=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --fresh) FRESH=1; shift ;;
        --revision) REVISION="${2:?Missing revision}"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ "$REPO" == /* && "$REPO" != / && "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || exit 2
[[ -z "$REVISION" || "$REVISION" =~ ^[0-9a-f]{40}$ ]] || exit 2
cd "$REPO"
[[ -z "$(git status --porcelain)" ]] || { echo "Server checkout is dirty; refusing to overwrite it" >&2; exit 2; }
BEFORE=$(git rev-parse HEAD)

echo "==> [1/6] Update code"
if [[ -n "$REVISION" ]]; then
    git fetch "$BUNDLE" main
    [[ "$(git rev-parse FETCH_HEAD)" == "$REVISION" ]] || { echo "Bundle/revision mismatch" >&2; exit 2; }
    git merge --ff-only "$REVISION"
else
    GIT_TERMINAL_PROMPT=0 git -c http.version=HTTP/1.1 pull --ff-only origin main \
        || git pull --ff-only "$BUNDLE" main
fi
AFTER=$(git rev-parse HEAD)
[[ -z "$REVISION" || "$AFTER" == "$REVISION" ]] || exit 2
printf 'Release: %s -> %s\n' "$BEFORE" "$AFTER"

DC=(docker compose --project-name "$PROJECT" --env-file deploy/app.env --env-file deploy/runner.env
    -f docker-compose.app.yml -f docker-compose.runner.yml)
# Parse only non-secret fields; never print expanded config (contains API keys).
CONFIG=$("${DC[@]}" --profile sandbox config --format json)
SANDBOX_IMAGE=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["sandbox-image"]["image"])' <<< "$CONFIG")
python3 -c '
import json,sys
c=json.load(sys.stdin)
url=c["services"]["migrate"]["environment"]["DATABASE_URL"]
assert url in {"sqlite+aiosqlite:///./data/learn_da.db", "sqlite+aiosqlite:////app/data/learn_da.db"}, "Release backup/reset supports only the project SQLite database in /app/data"
' <<< "$CONFIG"
mapfile -t VOLUMES < <(python3 -c '
import json,sys
c=json.load(sys.stdin)
assert set(c["volumes"]) == {"learn_da_data", "learn_da_logs"}
for k,v in c["volumes"].items():
    assert not v.get("external"), "External volumes cannot be reset"
    print(k + " " + v["name"])
' <<< "$CONFIG")
[[ ${#VOLUMES[@]} -eq 2 ]] || { echo "Unexpected volume configuration" >&2; exit 2; }
unset CONFIG

echo "==> [2/6] Build images (sequentially to limit memory)"
# Always consult Docker's content cache: after a failed update Git HEAD may
# already equal the target while the old image tag still exists.
echo "Sandbox: $SANDBOX_IMAGE"
"${DC[@]}" --profile sandbox build sandbox-image
for service in backend migrate runner web; do
    "${DC[@]}" build "$service"
done
# The build tag selects the newly built image even if an old container exists.
BACKEND_IMAGE=$(docker image inspect "$PROJECT-backend" --format '{{.Id}}')

echo "==> [3/6] Stop application writers and back up project volumes"
"${DC[@]}" stop web backend
BACKUP_DIR="${LEARN_DA_BACKUP_ROOT:-/var/backups/learn_da}/$(date -u +%Y%m%dT%H%M%SZ)-${AFTER:0:12}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
printf '%s\n' "$BEFORE" > "$BACKUP_DIR/previous-revision.txt"
for entry in "${VOLUMES[@]}"; do
    read -r logical volume <<< "$entry"
    if docker volume inspect "$volume" >/dev/null 2>&1; then
        owner=$(docker volume inspect "$volume" --format '{{index .Labels "com.docker.compose.project"}}')
        key=$(docker volume inspect "$volume" --format '{{index .Labels "com.docker.compose.volume"}}')
        [[ "$owner" == "$PROJECT" && "$key" == "$logical" ]] || { echo "Volume ownership mismatch: $volume" >&2; exit 2; }
        docker run --rm --network none --user 0 --entrypoint python \
            --mount "type=volume,source=$volume,target=/source,readonly" \
            --mount "type=bind,source=$BACKUP_DIR,target=/backup" \
            "$BACKEND_IMAGE" -c 'import sys,tarfile; t=tarfile.open("/backup/"+sys.argv[1]+".tar.gz","w:gz"); t.add("/source",arcname="."); t.close()' "$logical"
    fi
done
echo "Backup: $BACKUP_DIR"
if [[ "$FRESH" == 1 ]]; then
    "${DC[@]}" down
    for entry in "${VOLUMES[@]}"; do
        read -r logical volume <<< "$entry"
        if docker volume inspect "$volume" >/dev/null 2>&1; then
            docker volume rm "$volume"
        fi
    done
fi

echo "==> [4/6] Start Runner, migrate database, start Backend/Web"
"${DC[@]}" up -d --no-deps --wait --wait-timeout 120 runner
"${DC[@]}" run --rm --no-deps migrate
"${DC[@]}" up -d --no-deps --wait --wait-timeout 180 backend
"${DC[@]}" up -d --no-deps --wait --wait-timeout 60 web

echo "==> [5/6] Production acceptance (creates an isolated acceptance visitor)"
PORT=$("${DC[@]}" port web 80 | head -1 | awk -F: '{print $NF}')
LEARN_DA_BASE_URL="http://127.0.0.1:$PORT" bash deploy/acceptance.sh

echo "==> [6/6] Release state"
"${DC[@]}" ps
printf 'Deployed %s; fresh=%s; backup=%s\n' "$AFTER" "$FRESH" "$BACKUP_DIR"
