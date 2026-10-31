#!/usr/bin/env bash
# Isolated release-flow regression checks. Never talks to Docker or a server.
set -euo pipefail
SOURCE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin" "$WORK/repo/deploy"
cp "$SOURCE/update.sh" "$SOURCE/push-deploy.sh" "$WORK/repo/deploy/"
export RELEASE_TEST_LOG="$WORK/calls" LEARN_DA_REPO="$WORK/repo" LEARN_DA_SERVER=fake
export PATH="$WORK/bin:$PATH"
# Windows can have a nonfunctional python3 Store alias; use a real interpreter.
if ! python3 -c 'print(1)' 2>/dev/null | grep -q 1; then
    cat > "$WORK/bin/python3" <<'SH'
#!/usr/bin/env bash
exec python "$@"
SH
fi
cat > "$WORK/bin/git" <<'SH'
#!/usr/bin/env bash
echo "git $*" >> "$RELEASE_TEST_LOG"
case "$*" in
  'status --porcelain') [[ ${TEST_DIRTY:-0} == 0 ]] || echo ' M pending.py' ;;
  'branch --show-current') echo main ;;
  'rev-parse '*) printf '%040d\n' 1 ;;
esac
exit 0
SH
cat > "$WORK/bin/docker" <<'SH'
#!/usr/bin/env bash
echo "docker $*" >> "$RELEASE_TEST_LOG"
case "$*" in
  *'config --format json') printf '%s\n' '{"services":{"sandbox-image":{"image":"sandbox:pinned"},"migrate":{"environment":{"DATABASE_URL":"sqlite+aiosqlite:///./data/learn_da.db"}}},"volumes":{"learn_da_data":{"name":"learn_da_learn_da_data"},"learn_da_logs":{"name":"learn_da_learn_da_logs"}}}' ;;
  'image inspect sandbox:pinned') [[ ${TEST_SANDBOX_EXISTS:-0} == 1 ]] || exit 1 ;;
  *'images -q backend') echo backend-image ;;
  'volume inspect '*com.docker.compose.project*) echo "${TEST_OWNER:-learn_da}" ;;
  'volume inspect '*com.docker.compose.volume*)
    if [[ "$*" == *learn_da_learn_da_data* ]]; then echo learn_da_data; else echo learn_da_logs; fi ;;
  'run --rm --network none'*) [[ ${TEST_BACKUP_FAIL:-0} == 0 ]] || exit 9 ;;
  *'port web 80') echo 0.0.0.0:80 ;;
esac
SH
cat > "$WORK/repo/deploy/acceptance.sh" <<'SH'
#!/usr/bin/env bash
echo acceptance >> "$RELEASE_TEST_LOG"
SH
chmod +x "$WORK/bin/"*
export LEARN_DA_BACKUP_ROOT="$WORK/backups"

: > "$RELEASE_TEST_LOG"
if TEST_DIRTY=1 bash "$WORK/repo/deploy/push-deploy.sh" > "$WORK/dirty.log" 2>&1; then
    echo 'FAIL: dirty checkout was released'; exit 1
fi
! grep -qE 'git push|docker|scp|ssh' "$RELEASE_TEST_LOG"
echo 'PASS dirty checkout is rejected before network access'

: > "$RELEASE_TEST_LOG"
if TEST_OWNER=unrelated bash "$WORK/repo/deploy/update.sh" --fresh > "$WORK/owner.log" 2>&1; then
    echo 'FAIL: unrelated volume was accepted'; exit 1
fi
! grep -qE 'volume rm| down$|docker run' "$RELEASE_TEST_LOG"
echo 'PASS unrelated volume ownership prevents backup/reset'

: > "$RELEASE_TEST_LOG"
if TEST_BACKUP_FAIL=1 bash "$WORK/repo/deploy/update.sh" --fresh > "$WORK/backup.log" 2>&1; then
    echo 'FAIL: failed backup was ignored'; exit 1
fi
! grep -qE 'volume rm| down$' "$RELEASE_TEST_LOG"
echo 'PASS backup failure prevents data reset'

: > "$RELEASE_TEST_LOG"
bash "$WORK/repo/deploy/update.sh" --fresh > "$WORK/fresh.log" 2>&1 || { cat "$WORK/fresh.log"; exit 1; }
python3 - "$RELEASE_TEST_LOG" <<'PY'
import sys
calls=open(sys.argv[1]).read().splitlines()
def at(text):
    return next(i for i,line in enumerate(calls) if text in line)
assert at('build sandbox-image') < at('stop web backend')
assert at('--entrypoint python') < at(' down') < at('volume rm')
removed=[line for line in calls if 'volume rm' in line]
assert removed == ['docker volume rm learn_da_learn_da_data', 'docker volume rm learn_da_learn_da_logs']
assert at('--wait-timeout 120 runner') < at('run --rm --no-deps migrate') < at('--wait-timeout 180 backend') < at('--wait-timeout 60 web') < at('acceptance')
PY
echo 'PASS fresh release backs up, resets only owned volumes, waits for services and runs acceptance'

: > "$RELEASE_TEST_LOG"
bash "$WORK/repo/deploy/update.sh" > "$WORK/update.log" 2>&1
! grep -qE 'volume rm| down$' "$RELEASE_TEST_LOG"
echo 'PASS default update preserves existing data'

: > "$RELEASE_TEST_LOG"
TEST_SANDBOX_EXISTS=1 bash "$WORK/repo/deploy/update.sh" > "$WORK/retry.log" 2>&1
grep -q 'build sandbox-image' "$RELEASE_TEST_LOG"
echo 'PASS same-revision retry rebuilds the sandbox even when its old tag exists'
