#!/usr/bin/env bash
# Learn DA 生产部署验收脚本（改版 M4 / 学习工作区链路）
#
# 用法（Git Bash / Linux，需要 curl + python3）：
#   bash deploy/acceptance.sh                    # 默认验收 http://127.0.0.1:8000
#   LEARN_DA_BASE_URL=http://other-host bash deploy/acceptance.sh
#
# 覆盖内容（练习时代的三课 validator 冒烟已随旧链路下线，改为工作区端到端）：
#   工作区建会话 -> 起步格真实执行 -> 起步代码提交判失败并回传实际断言值 ->
#   参考解逐格执行 -> 两个任务提交通过 -> 提交幂等重放 -> 改上游格触发 stale ->
#   进度/报告接口 -> 事件上报幂等 -> Agent 证据驱动教学反馈（含跨访客隔离）。
#
# 注意：
#   * 脚本会以全新匿名访客身份写入验收数据（会话、RunEvent、TaskAttempt、
#     analytics 事件、Agent interaction），每次运行产生一批新数据。
#   * 需要 Runner 可用：工作区执行只走 Runner，不可用时明确 503 fail-closed。
#   * Agent 检查会调用真实 LLM，耗时较长；模型不可用时回答正文是
#     "AI 助手暂时不可用"，但 teachingFeedback 仍由服务端给出（属预期降级）。
set -uo pipefail

BASE="${LEARN_DA_BASE_URL:-http://127.0.0.1:8000}"
API="$BASE/api/v1"

# 选一个真的能跑的 python：Windows 上 `python3` 常是应用商店占位程序，
# `command -v` 能找到但它什么都不执行（会静默产出空 JSON 结果，把所有检查拖垮）。
pick_python() {
  for candidate in python3 python; do
    path="$(command -v "$candidate" 2>/dev/null || true)"
    [ -n "$path" ] || continue
    if "$path" -c "print(1)" 2>/dev/null | grep -q 1; then
      echo "$path"
      return 0
    fi
  done
  return 1
}

PY="$(pick_python || true)"

if [ -z "$PY" ]; then
  echo "FATAL: 未找到可用的 python3/python（需要能执行 -c 的解释器），无法解析 JSON" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
JAR="$WORK/cookies.txt"
JAR_FRESH="$WORK/cookies_fresh.txt"
: > "$JAR"
: > "$JAR_FRESH"

PASS=0
FAIL=0
FAILURES=()

ok()   { PASS=$((PASS + 1)); echo "  PASS  $1"; }
bad()  { FAIL=$((FAIL + 1)); FAILURES+=("$1 -- $2"); echo "  FAIL  $1 -- $2"; }

# json_path FILE path.to.field  -> 取值（null/缺失输出空串）
json_path() {
  "$PY" - "$1" "$2" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        d = json.load(fh)
except Exception:
    print("")
    sys.exit(0)
for key in sys.argv[2].split("."):
    if isinstance(d, list):
        try:
            d = d[int(key)]
        except Exception:
            d = None
            break
    elif isinstance(d, dict):
        d = d.get(key)
    else:
        d = None
        break
print("" if d is None else d)
PYEOF
}

# req METHOD PATH JAR OUT -> 输出 HTTP 状态码
req() {
  curl -s -o "$4" -w "%{http_code}" --max-time 120 \
    -c "$3" -b "$3" -X "$1" "$API$2"
}

# 注意：payload 一律先落到文件，再用 `--data-binary @file` 发送。
# 不能写成 `-d "$payload"` —— 在 Git Bash（MSYS）里，命令行参数传给原生
# curl.exe 时会被转成系统 ANSI 代码页，UTF-8 的中文会变成非法字节，
# 后端直接回 400 "There was an error parsing the body"。
PAYLOAD="$WORK/payload.json"

post_json() { # PATH PAYLOAD JAR OUT
  printf '%s' "$2" > "$PAYLOAD"
  curl -s -o "$4" -w "%{http_code}" --max-time 120 \
    -c "$3" -b "$3" -H "Content-Type: application/json" \
    --data-binary "@$PAYLOAD" "$API$1"
}

put_json() { # PATH PAYLOAD JAR OUT
  printf '%s' "$2" > "$PAYLOAD"
  curl -s -o "$4" -w "%{http_code}" --max-time 120 \
    -c "$3" -b "$3" -H "Content-Type: application/json" \
    -X PUT --data-binary "@$PAYLOAD" "$API$1"
}

new_rid() { "$PY" -c "import uuid; print(uuid.uuid4().hex)"; }

# field_of FILE taskId key -> 取 tasks 里某个任务的某个字段
task_field() {
  "$PY" - "$1" "$2" "$3" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8")).get("data") or {}
    hit = [x for x in (d.get("tasks") or []) if x.get("taskId") == sys.argv[2]]
    print(hit[0].get(sys.argv[3]) if hit else "")
except Exception:
    print("")
PYEOF
}

echo "=== Learn DA 生产部署验收（学习工作区链路）==="
echo "BASE = $BASE"
echo

LESSON="polars-groupby"

# ---------- A1 后端可达 + 内容索引 ----------
echo "[A1] 后端可达性与内容索引"
code=$(req GET /lessons "$JAR" "$WORK/lessons.json")
lessons_len=$("$PY" -c "
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8'))
    print(len(d.get('data') or []))
except Exception:
    print(-1)" "$WORK/lessons.json")
if [ "$code" = "200" ] && [ "$lessons_len" = "13" ]; then
  ok "GET /lessons 返回 13 门课程（ContentIndex 构建正常）"
else
  bad "GET /lessons" "http=$code lessons=$lessons_len（期望 200/13）"
fi

# ---------- A2 签名匿名会话 ----------
echo "[A2] 签名匿名会话 cookie"
# 注：/lessons 不依赖访客身份，不触发 cookie 签发；用需要身份的端点验证
code=$(req GET /workspace/progress "$JAR" "$WORK/progress0.json")
if [ "$code" = "200" ] && [ "$(json_path "$WORK/progress0.json" code)" = "200" ]; then
  ok "GET /workspace/progress 携带会话可读"
else
  bad "GET /workspace/progress" "http=$code body=$(head -c 200 "$WORK/progress0.json" 2>/dev/null)"
fi
if grep -q "learn_da_session" "$JAR"; then
  if grep "learn_da_session" "$JAR" | grep -qi "secure"; then
    # 明文 HTTP 部署下 Secure cookie 会被浏览器拒收（2026-08-17 验收发现的缺陷）
    bad "会话 cookie" "cookie 带 Secure 属性，明文 HTTP 下浏览器将拒收"
  else
    ok "会话 cookie learn_da_session 已签发且未带 Secure（适配明文 HTTP）"
  fi
else
  bad "会话 cookie" "响应未设置 learn_da_session"
fi

# ---------- A3 创建工作区会话 ----------
echo "[A3] 创建工作区会话（$LESSON）"
code=$(post_json /workspace/sessions "{\"lessonSlug\":\"$LESSON\"}" "$JAR" "$WORK/session.json")
SID=$(json_path "$WORK/session.json" data.sessionId)
DATASETS=$(json_path "$WORK/session.json" data.datasets)
cell_count=$("$PY" -c "
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8')).get('data') or {}
    print(len(d.get('cells') or []), len(d.get('tasks') or []))
except Exception:
    print(-1, -1)" "$WORK/session.json")
if [ "$code" = "200" ] && [ -n "$SID" ]; then
  ok "创建会话 sessionId=$SID（$cell_count 个单元格/任务，数据集 $DATASETS）"
else
  bad "创建工作区会话" "http=$code body=$(head -c 300 "$WORK/session.json")"
fi

# ---------- A4 起步格真实执行 ----------
echo "[A4] 起步格真实执行（Runner）"
code=$(post_json "/workspace/sessions/$SID/cells/c1/run" "{\"requestId\":\"$(new_rid)\"}" "$JAR" "$WORK/run_c1.json")
verdict=$(json_path "$WORK/run_c1.json" data.verdict)
dur=$(json_path "$WORK/run_c1.json" data.durationMs)
if [ "$code" = "200" ] && [ "$verdict" = "passed" ]; then
  ok "c1 起步格执行成功（verdict=$verdict，${dur}ms）"
else
  bad "c1 起步格执行" "http=$code verdict=$verdict body=$(head -c 300 "$WORK/run_c1.json")"
fi

# ---------- A5 起步代码提交必须判失败并回传真实断言值 ----------
echo "[A5] 起步代码提交必须判失败（判定不能放水）"
code=$(post_json "/workspace/sessions/$SID/tasks/t1/submit" "{\"requestId\":\"$(new_rid)\"}" "$JAR" "$WORK/t1_fail.json")
v_fail=$(json_path "$WORK/t1_fail.json" data.verdict)
s_fail=$(json_path "$WORK/t1_fail.json" data.taskStatus)
has_actual=$("$PY" -c "
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8')).get('data') or {}
    items=d.get('assertions') or []
    print('1' if any(i.get('status')!='passed' and (i.get('actual') or i.get('detail')) for i in items) else '0')
except Exception:
    print('0')" "$WORK/t1_fail.json")
if [ "$code" = "200" ] && [ "$v_fail" = "assertion_failed" ] && [ "$s_fail" = "failed" ] && [ "$has_actual" = "1" ]; then
  ok "起步代码判 assertion_failed 且回传实际值（taskStatus=$s_fail）"
else
  bad "起步代码应判失败" "http=$code verdict=$v_fail taskStatus=$s_fail 有实际值=$has_actual body=$(head -c 300 "$WORK/t1_fail.json")"
fi

# ---------- A6 参考解逐格执行并提交通过 ----------
echo "[A6] 参考解逐格执行并提交通过"

cat > "$WORK/c2.json" <<'EOF'
{"code":"region_stats = (\n    orders.group_by('region')\n    .agg(\n        pl.col('amount').sum().alias('revenue'),\n        pl.len().alias('orders'),\n    )\n    .sort('revenue', descending=True)\n)\nprint(region_stats)\n"}
EOF
code=$(put_json "/workspace/sessions/$SID/cells/c2" "$(cat "$WORK/c2.json")" "$JAR" "$WORK/c2_put.json")
[ "$code" = "200" ] && ok "写入 c2 参考解（按区域聚合）" || bad "写入 c2" "http=$code body=$(head -c 300 "$WORK/c2_put.json")"

RID_T1=$(new_rid)
code=$(post_json "/workspace/sessions/$SID/tasks/t1/submit" "{\"requestId\":\"$RID_T1\"}" "$JAR" "$WORK/t1_pass.json")
v_pass=$(json_path "$WORK/t1_pass.json" data.verdict)
s_pass=$(json_path "$WORK/t1_pass.json" data.taskStatus)
passed_n=$("$PY" -c "
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8')).get('data') or {}
    print(len([i for i in (d.get('assertions') or []) if i.get('status')=='passed']))
except Exception:
    print(0)" "$WORK/t1_pass.json")
if [ "$code" = "200" ] && [ "$v_pass" = "passed" ] && [ "$s_pass" = "passed" ] && [ "${passed_n:-0}" -ge 3 ] 2>/dev/null; then
  ok "t1 参考解通过（$passed_n 条断言全过，taskStatus=$s_pass）"
else
  bad "t1 参考解应通过" "http=$code verdict=$v_pass taskStatus=$s_pass passed=$passed_n body=$(head -c 400 "$WORK/t1_pass.json")"
fi

cat > "$WORK/c3.json" <<'EOF'
{"code":"region_share = region_stats.with_columns(\n    (pl.col('revenue') / pl.col('revenue').sum()).round(2).alias('share')\n)\nprint(region_share)\n"}
EOF
code=$(put_json "/workspace/sessions/$SID/cells/c3" "$(cat "$WORK/c3.json")" "$JAR" "$WORK/c3_put.json")
[ "$code" = "200" ] && ok "写入 c3 参考解（计算占比）" || bad "写入 c3" "http=$code body=$(head -c 300 "$WORK/c3_put.json")"

code=$(post_json "/workspace/sessions/$SID/tasks/t2/submit" "{\"requestId\":\"$(new_rid)\"}" "$JAR" "$WORK/t2_pass.json")
v2=$(json_path "$WORK/t2_pass.json" data.verdict)
s2=$(json_path "$WORK/t2_pass.json" data.taskStatus)
if [ "$code" = "200" ] && [ "$v2" = "passed" ] && [ "$s2" = "passed" ]; then
  ok "t2 参考解通过（taskStatus=$s2）"
else
  bad "t2 参考解应通过" "http=$code verdict=$v2 taskStatus=$s2 body=$(head -c 400 "$WORK/t2_pass.json")"
fi

# ---------- A7 提交幂等重放 ----------
echo "[A7] 相同 requestId 重放幂等"
code=$(post_json "/workspace/sessions/$SID/tasks/t1/submit" "{\"requestId\":\"$RID_T1\"}" "$JAR" "$WORK/t1_replay.json")
v_replay=$(json_path "$WORK/t1_replay.json" data.verdict)
if [ "$code" = "200" ] && [ -n "$v_pass" ] && [ "$v_replay" = "$v_pass" ]; then
  ok "重放返回同一结论 verdict=$v_replay（未新建 TaskAttempt）"
else
  bad "提交幂等重放" "http=$code 首次=$v_pass 重放=$v_replay"
fi

# ---------- A8 进度与报告接口 ----------
echo "[A8] 进度与报告接口"
code=$(req GET /workspace/progress "$JAR" "$WORK/progress1.json")
tasks_passed=$(json_path "$WORK/progress1.json" data.summary.tasksPassed)
lessons_started=$(json_path "$WORK/progress1.json" data.summary.lessonsStarted)
lesson_status=$("$PY" -c "
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8')).get('data') or {}
    hit=[x for x in (d.get('lessons') or []) if x.get('lessonSlug')=='$LESSON']
    print(hit[0].get('status') if hit else '')
except Exception:
    print('')" "$WORK/progress1.json")
if [ "$code" = "200" ] && [ "${tasks_passed:-0}" -ge 2 ] 2>/dev/null && [ "$lesson_status" = "completed" ]; then
  ok "progress：tasksPassed=$tasks_passed lessonsStarted=$lessons_started 该课=$lesson_status"
else
  bad "workspace/progress" "http=$code tasksPassed=$tasks_passed status=$lesson_status body=$(head -c 300 "$WORK/progress1.json")"
fi

code=$(req GET /workspace/report "$JAR" "$WORK/report.json")
report_keys=$("$PY" -c "
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8')).get('data') or {}
    need={'lessonProgress','tracks','summary','errorPatterns','recent'}
    print('1' if need <= set(d) else '0')
except Exception:
    print('0')" "$WORK/report.json")
recent_len=$("$PY" -c "
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8')).get('data') or {}
    print(len(d.get('recent') or []))
except Exception:
    print(-1)" "$WORK/report.json")
if [ "$code" = "200" ] && [ "$report_keys" = "1" ] && [ "${recent_len:-0}" -ge 1 ] 2>/dev/null; then
  ok "report：字段齐全，recent 有 $recent_len 条真实提交"
else
  bad "workspace/report" "http=$code keys_ok=$report_keys recent=$recent_len"
fi

# ---------- A9 Agent 证据驱动教学反馈 ----------
echo "[A9] Agent 教学反馈（真实 LLM，耗时较长）"

# A9a 全新访客 -> no_evidence
code=$(post_json /agent/chat '{"message":"我该从哪里开始学？","history":[]}' "$JAR_FRESH" "$WORK/chat0.json")
state0=$(json_path "$WORK/chat0.json" data.teachingFeedback.state)
if [ "$code" = "200" ] && [ "$state0" = "no_evidence" ]; then
  ok "新访客无提交证据 -> state=no_evidence"
else
  bad "no_evidence 场景" "http=$code state=$state0 body=$(head -c 300 "$WORK/chat0.json")"
fi

# A9b 有通过的提交 -> passed_unconfirmed（证据取 payload.context.currentLesson）
code=$(post_json /agent/chat "{\"message\":\"我这两步做对了吗？\",\"history\":[],\"context\":{\"currentLesson\":\"$LESSON\",\"currentTask\":\"t2\"}}" "$JAR" "$WORK/chat1.json")
state1=$(json_path "$WORK/chat1.json" data.teachingFeedback.state)
next1=$(json_path "$WORK/chat1.json" data.teachingFeedback.nextAction)
hint1=$(json_path "$WORK/chat1.json" data.teachingFeedback.hintLevel)
if [ "$code" = "200" ] && [ "$state1" = "passed_unconfirmed" ] && [ -n "$next1" ]; then
  ok "通过的任务提交 -> state=$state1 nextAction=$next1 hintLevel=$hint1"
else
  bad "passed_unconfirmed 场景" "http=$code state=$state1 nextAction=$next1 body=$(head -c 300 "$WORK/chat1.json")"
fi

# A9c 伪造他人 attemptId -> 不得解析出证据（跨访客隔离）
code=$(post_json /agent/chat "{\"message\":\"帮我看看这次提交\",\"history\":[],\"context\":{\"currentLesson\":\"$LESSON\",\"attemptId\":999999999}}" "$JAR_FRESH" "$WORK/chat2.json")
state2=$(json_path "$WORK/chat2.json" data.teachingFeedback.state)
if [ "$code" = "200" ] && [ "$state2" = "no_evidence" ]; then
  ok "伪造 attemptId 无法获得他人证据（跨访客隔离）"
else
  bad "跨访客证据隔离" "http=$code state=$state2（非 no_evidence 说明隔离失效）"
fi

# ---------- A10 改上游格触发严格顺序失效 ----------
echo "[A10] 改上游代码 -> 下游失效（严格顺序语义）"
cat > "$WORK/c2_edit.json" <<'EOF'
{"code":"# 改一行注释，验证下游失效\nregion_stats = (\n    orders.group_by('region')\n    .agg(\n        pl.col('amount').sum().alias('revenue'),\n        pl.len().alias('orders'),\n    )\n    .sort('revenue', descending=True)\n)\nprint(region_stats)\n"}
EOF
code=$(put_json "/workspace/sessions/$SID/cells/c2" "$(cat "$WORK/c2_edit.json")" "$JAR" "$WORK/c2_edit_put.json")
stale_from=$(json_path "$WORK/c2_edit_put.json" data.staleFrom)
t1_after=$(task_field "$WORK/c2_edit_put.json" t1 status)
if [ "$code" = "200" ] && [ "$stale_from" = "c2" ] && [ "$t1_after" = "todo" ]; then
  ok "改 c2 -> staleFrom=c2，已通过的 t1 回退 todo（需复核，历史提交不改）"
else
  bad "严格顺序失效" "http=$code staleFrom=$stale_from t1=$t1_after body=$(head -c 300 "$WORK/c2_edit_put.json")"
fi

# ---------- A11 事件上报幂等与进度投影 ----------
echo "[A11] /analytics/track 幂等与进度投影"
EID_C=$(new_rid)
code=$(post_json /analytics/track "{\"eventType\":\"lesson_complete\",\"lessonSlug\":\"$LESSON\",\"eventId\":\"$EID_C\"}" "$JAR" "$WORK/track1.json")
[ "$code" = "200" ] && ok "lesson_complete 上报成功" || bad "lesson_complete" "http=$code body=$(head -c 200 "$WORK/track1.json")"

req GET /learner-state/progress "$JAR" "$WORK/ls1.json" > /dev/null
total1=$(json_path "$WORK/ls1.json" data.totalCompleted)
post_json /analytics/track "{\"eventType\":\"lesson_complete\",\"lessonSlug\":\"$LESSON\",\"eventId\":\"$EID_C\"}" "$JAR" "$WORK/track2.json" > /dev/null
req GET /learner-state/progress "$JAR" "$WORK/ls2.json" > /dev/null
total2=$(json_path "$WORK/ls2.json" data.totalCompleted)
if [ -n "$total1" ] && [ "$total1" = "$total2" ]; then
  ok "相同 eventId 重放不改变 totalCompleted（=$total2）"
else
  bad "事件幂等" "重放前=$total1 重放后=$total2"
fi

# ---------- 汇总 ----------
echo
echo "=== 验收汇总 ==="
echo "通过：$PASS  失败：$FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "失败项："
  for f in "${FAILURES[@]}"; do echo "  - $f"; done
  exit 1
fi
echo "全部检查通过。"
