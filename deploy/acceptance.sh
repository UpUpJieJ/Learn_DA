#!/usr/bin/env bash
# Learn DA 生产部署验收脚本
#
# 用法（Git Bash / Linux，需要 curl + python3）：
#   bash deploy/acceptance.sh                    # 默认验收 http://43.142.89.100
#   LEARN_DA_BASE_URL=http://other-host bash deploy/acceptance.sh
#
# 覆盖 phase3/phase4 完成总结中遗留的"服务器部署验收"：
#   三节样板课程真实 Runner 执行 -> 练习判定 -> Attempt 落库 ->
#   Agent 证据驱动教学反馈 -> 事件幂等 -> Dashboard 练习指标。
#
# 注意：脚本会以全新匿名访客身份写入验收数据（执行记录、Attempt、
# analytics 事件、Agent interaction），每次运行产生一批新数据。
set -uo pipefail

BASE="${LEARN_DA_BASE_URL:-http://43.142.89.100}"
API="$BASE/api/v1"
PY="$(command -v python3 || command -v python || true)"

if [ -z "$PY" ]; then
  echo "FATAL: 未找到 python3/python，无法解析 JSON" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
JAR="$WORK/cookies.txt"
JAR_FRESH="$WORK/cookies_fresh.txt"
: > "$JAR"

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

post_json() { # PATH PAYLOAD JAR OUT
  curl -s -o "$4" -w "%{http_code}" --max-time 120 \
    -c "$3" -b "$3" -H "Content-Type: application/json" \
    -d "$2" "$API$1"
}

echo "=== Learn DA 生产部署验收 ==="
echo "BASE = $BASE"
echo

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
if grep -q "learn_da_session" "$JAR"; then
  ok "会话 cookie learn_da_session 已签发"
else
  bad "会话 cookie" "响应未设置 learn_da_session"
fi
code=$(req GET /learner-state/progress "$JAR" "$WORK/progress0.json")
if [ "$code" = "200" ] && [ "$(json_path "$WORK/progress0.json" code)" = "200" ]; then
  ok "GET /learner-state/progress 携带会话可读"
else
  bad "GET /learner-state/progress" "http=$code body=$(head -c 200 "$WORK/progress0.json" 2>/dev/null)"
fi

# ---------- A3 三节样板课程：正确答案 -> 验证通过 ----------
echo "[A3] 三节样板课程练习通过（真实 Runner 执行）"

# 01 polars-basics（dataframe_rows）
cat > "$WORK/ex01.json" <<'EOF'
{"code":"import polars as pl\n\norders = pl.DataFrame({\n    'product': ['键盘', '鼠标', '显示器', '耳机'],\n    'price': [200, 80, 1500, 300],\n    'quantity': [3, 5, 1, 2],\n})\n\nresult = orders.filter(pl.col('price') > 100).select('product', 'price')\nprint(result)\n","language":"python","lessonSlug":"01-polars-basics","exerciseId":"polars-basics-filter-select-v1"}
EOF
RID01=$("$PY" -c "import uuid; print(uuid.uuid4())")
"$PY" -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8')); d['requestId']=sys.argv[2]
json.dump(d, open(sys.argv[1],'w',encoding='utf-8'), ensure_ascii=False)" \
  "$WORK/ex01.json" "$RID01"
code=$(post_json /playground/execute "$(cat "$WORK/ex01.json")" "$JAR" "$WORK/ex01r.json")
vstatus=$(json_path "$WORK/ex01r.json" data.verification.status)
ATYPE01=$(json_path "$WORK/ex01r.json" data.attemptId)
if [ "$code" = "200" ] && [ "$(json_path "$WORK/ex01r.json" data.status)" = "success" ] \
   && [ "$vstatus" = "passed" ] && [ -n "$ATYPE01" ]; then
  ok "01-polars-basics 验证通过（dataframe_rows，attemptId=$ATYPE01）"
else
  bad "01-polars-basics 通过执行" "http=$code status=$(json_path "$WORK/ex01r.json" data.status) verification=$vstatus body=$(head -c 300 "$WORK/ex01r.json")"
fi

# 07 duckdb-sql-foundations（stdout_exact）
cat > "$WORK/ex07.json" <<'EOF'
{"code":"import duckdb\n\ncon = duckdb.connect()\ncon.execute(\"\"\"\n    CREATE TABLE orders AS\n    SELECT * FROM (VALUES\n        (1, '华东', '办公', 120),\n        (2, '华东', '数码', 899),\n        (3, '华南', '办公', 240),\n        (4, '华北', '配件', 59)\n    ) AS t(order_id, region, category, amount)\n\"\"\")\n\nresult = con.execute(\"\"\"\n    SELECT category, COUNT(*) AS order_count, SUM(amount) AS total_amount\n    FROM orders\n    GROUP BY category\n    HAVING SUM(amount) > 200\n    ORDER BY total_amount DESC\n\"\"\").fetchall()\n\nprint(result)\n","language":"python","lessonSlug":"07-duckdb-sql-foundations","exerciseId":"duckdb-sql-groupby-having-v1"}
EOF
RID07=$("$PY" -c "import uuid; print(uuid.uuid4())")
"$PY" -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8')); d['requestId']=sys.argv[2]
json.dump(d, open(sys.argv[1],'w',encoding='utf-8'), ensure_ascii=False)" \
  "$WORK/ex07.json" "$RID07"
code=$(post_json /playground/execute "$(cat "$WORK/ex07.json")" "$JAR" "$WORK/ex07r.json")
vstatus=$(json_path "$WORK/ex07r.json" data.verification.status)
ATYPE07=$(json_path "$WORK/ex07r.json" data.attemptId)
if [ "$code" = "200" ] && [ "$vstatus" = "passed" ] && [ -n "$ATYPE07" ]; then
  ok "07-duckdb-sql-foundations 验证通过（stdout_exact，attemptId=$ATYPE07）"
else
  bad "07-duckdb-sql-foundations 通过执行" "http=$code verification=$vstatus stdout=$(head -c 200 "$WORK/ex07r.json")"
fi

# 12 python-functions（stdout_exact）
cat > "$WORK/ex12.json" <<'EOF'
{"code":"def add_bonus(score):\n    return score + 5\nprint(add_bonus(95))\n","language":"python","lessonSlug":"12-python-functions","exerciseId":"python-functions-add-bonus-v1"}
EOF
RID12=$("$PY" -c "import uuid; print(uuid.uuid4())")
"$PY" -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8')); d['requestId']=sys.argv[2]
json.dump(d, open(sys.argv[1],'w',encoding='utf-8'), ensure_ascii=False)" \
  "$WORK/ex12.json" "$RID12"
code=$(post_json /playground/execute "$(cat "$WORK/ex12.json")" "$JAR" "$WORK/ex12r.json")
vstatus=$(json_path "$WORK/ex12r.json" data.verification.status)
ATYPE12=$(json_path "$WORK/ex12r.json" data.attemptId)
if [ "$code" = "200" ] && [ "$vstatus" = "passed" ] && [ -n "$ATYPE12" ]; then
  ok "12-python-functions 验证通过（stdout_exact，attemptId=$ATYPE12）"
else
  bad "12-python-functions 通过执行" "http=$code verification=$vstatus body=$(head -c 200 "$WORK/ex12r.json")"
fi

# ---------- A4 错误答案必须判失败（validator 加固回归） ----------
echo "[A4] 全表输出不得判通过（validator 加固）"
cat > "$WORK/exbad.json" <<EOF
{"requestId":"$("$PY" -c "import uuid; print(uuid.uuid4())")","code":"import polars as pl\n\norders = pl.DataFrame({\n    'product': ['键盘', '鼠标', '显示器', '耳机'],\n    'price': [200, 80, 1500, 300],\n    'quantity': [3, 5, 1, 2],\n})\n\nresult = orders\nprint(result)\n","language":"python","lessonSlug":"01-polars-basics","exerciseId":"polars-basics-filter-select-v1"}
EOF
code=$(post_json /playground/execute "$(cat "$WORK/exbad.json")" "$JAR" "$WORK/exbadr.json")
vstatus=$(json_path "$WORK/exbadr.json" data.verification.status)
ATYPEBAD=$(json_path "$WORK/exbadr.json" data.attemptId)
if [ "$code" = "200" ] && [ "$vstatus" = "failed" ]; then
  ok "未筛选的全表输出被判定为 failed（attemptId=$ATYPEBAD）"
else
  bad "全表输出应判 failed" "http=$code verification=$vstatus（passed 说明 validator 存在漏洞）"
fi

# ---------- A5 Attempt 幂等重放 ----------
echo "[A5] 相同 requestId 重放幂等"
code=$(post_json /playground/execute "$(cat "$WORK/ex01.json")" "$JAR" "$WORK/ex01p.json")
ATYPE01P=$(json_path "$WORK/ex01p.json" data.attemptId)
if [ "$code" = "200" ] && [ -n "$ATYPE01" ] && [ "$ATYPE01P" = "$ATYPE01" ]; then
  ok "重放返回同一 attemptId=$ATYPE01（未新建 Attempt）"
else
  bad "Attempt 幂等重放" "http=$code 首次=$ATYPE01 重放=$ATYPE01P"
fi

# ---------- A6 事件上报幂等与 LearnerState 投影 ----------
echo "[A6] /analytics/track 幂等与进度投影"
EID_S=$("$PY" -c "import uuid; print(uuid.uuid4())")
EID_C=$("$PY" -c "import uuid; print(uuid.uuid4())")
code=$(post_json /analytics/track "{\"eventType\":\"lesson_start\",\"lessonSlug\":\"01-polars-basics\",\"eventId\":\"$EID_S\"}" "$JAR" "$WORK/track1.json")
[ "$code" = "200" ] && ok "lesson_start 上报成功" || bad "lesson_start" "http=$code body=$(head -c 200 "$WORK/track1.json")"
code=$(post_json /analytics/track "{\"eventType\":\"lesson_complete\",\"lessonSlug\":\"01-polars-basics\",\"eventId\":\"$EID_C\"}" "$JAR" "$WORK/track2.json")
[ "$code" = "200" ] && ok "lesson_complete 上报成功" || bad "lesson_complete" "http=$code body=$(head -c 200 "$WORK/track2.json")"

code=$(req GET /learner-state/progress "$JAR" "$WORK/progress1.json")
completed=$(json_path "$WORK/progress1.json" data.completedLessons)
total1=$(json_path "$WORK/progress1.json" data.totalCompleted)
if [ "$code" = "200" ] && echo "$completed" | grep -q "01-polars-basics"; then
  ok "进度投影包含已完成课程（totalCompleted=$total1）"
else
  bad "进度投影" "http=$code completedLessons=$completed"
fi

# 相同 eventId 重放，不得重复计数
post_json /analytics/track "{\"eventType\":\"lesson_complete\",\"lessonSlug\":\"01-polars-basics\",\"eventId\":\"$EID_C\"}" "$JAR" "$WORK/track3.json" > /dev/null
req GET /learner-state/progress "$JAR" "$WORK/progress2.json" > /dev/null
total2=$(json_path "$WORK/progress2.json" data.totalCompleted)
if [ -n "$total1" ] && [ "$total1" = "$total2" ] && [ "$total1" = "1" ]; then
  ok "相同 eventId 重放不改变 totalCompleted（=$total2）"
else
  bad "事件幂等" "重放前 totalCompleted=$total1 重放后=$total2（期望均为 1）"
fi

# ---------- A7 Agent 证据驱动教学反馈 ----------
echo "[A7] Agent 教学反馈（真实 LLM，耗时较长）"

# A7a 全新访客 -> no_evidence
code=$(post_json /agent/chat '{"message":"我该从哪里开始学？","history":[]}' "$JAR_FRESH" "$WORK/chat0.json")
state0=$(json_path "$WORK/chat0.json" data.teachingFeedback.state)
if [ "$code" = "200" ] && [ "$state0" = "no_evidence" ]; then
  ok "新访客无练习证据 -> state=no_evidence"
else
  bad "no_evidence 场景" "http=$code state=$state0 body=$(head -c 300 "$WORK/chat0.json")"
fi

# A7b 通过 attempt -> passed_unconfirmed
code=$(post_json /agent/chat "{\"message\":\"我的练习结果对吗？下一步做什么？\",\"history\":[],\"context\":{\"currentLesson\":\"01-polars-basics\",\"attemptId\":$ATYPE01}}" "$JAR" "$WORK/chat1.json")
state1=$(json_path "$WORK/chat1.json" data.teachingFeedback.state)
next1=$(json_path "$WORK/chat1.json" data.teachingFeedback.nextAction)
if [ "$code" = "200" ] && [ "$state1" = "passed_unconfirmed" ] && [ -n "$next1" ]; then
  ok "通过 Attempt -> state=passed_unconfirmed nextAction=$next1"
else
  bad "passed_unconfirmed 场景" "http=$code state=$state1 nextAction=$next1"
fi

# A7c 失败 attempt -> verification_failed
code=$(post_json /agent/chat "{\"message\":\"为什么我的练习没通过？\",\"history\":[],\"context\":{\"currentLesson\":\"01-polars-basics\",\"attemptId\":$ATYPEBAD}}" "$JAR" "$WORK/chat2.json")
state2=$(json_path "$WORK/chat2.json" data.teachingFeedback.state)
if [ "$code" = "200" ] && [ "$state2" = "verification_failed" ]; then
  ok "失败 Attempt -> state=verification_failed"
else
  bad "verification_failed 场景" "http=$code state=$state2"
fi

# A7d 伪造他人 attemptId -> 不得解析出证据（跨访客隔离）
code=$(post_json /agent/chat '{"message":"帮我看看这次尝试","history":[],"context":{"attemptId":999999999}}' "$JAR_FRESH" "$WORK/chat3.json")
state3=$(json_path "$WORK/chat3.json" data.teachingFeedback.state)
if [ "$code" = "200" ] && [ "$state3" = "no_evidence" ]; then
  ok "伪造 attemptId 无法获得他人证据（跨访客隔离）"
else
  bad "跨访客证据隔离" "http=$code state=$state3（非 no_evidence 说明隔离失效）"
fi

# ---------- A8 Dashboard 练习指标 ----------
echo "[A8] Dashboard 练习指标"
code=$(req GET /analytics/practice-stats "$JAR" "$WORK/stats.json")
keys_ok=$("$PY" -c "
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding='utf-8')).get('data') or {}
    need={'passedExercises','totalAttempts','helpThenPassRate','unresolvedFailures'}
    print('1' if need <= set(d) else '0')
except Exception:
    print('0')" "$WORK/stats.json")
passed_n=$(json_path "$WORK/stats.json" data.passedExercises)
if [ "$code" = "200" ] && [ "$keys_ok" = "1" ] && [ "${passed_n:-0}" -ge 3 ] 2>/dev/null; then
  ok "practice-stats 指标字段齐全，passedExercises=$passed_n（≥3）"
else
  bad "practice-stats" "http=$code keys_ok=$keys_ok passedExercises=$passed_n body=$(head -c 300 "$WORK/stats.json")"
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
