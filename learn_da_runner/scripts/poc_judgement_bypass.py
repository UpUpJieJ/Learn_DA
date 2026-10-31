"""判定越权 PoC 的可复现脚本（配套审查报告 learn_da/docs/refactor-review-2026-10-26.md 附录 A）。

用法（在仓库根目录）：
    learn_da_runner/.venv/Scripts/python.exe learn_da_runner/scripts/poc_judgement_bypass.py

每个 PoC 都会建一个独立临时目录，复制**真实的** session_driver.py（判定
parent）、learner_child.py（学员子进程）与 assertion_runtime.py，写
{cells, stopAt} 的 plan.json，把判定材料（assertions/refs/runtime/nonce）
经 stdin 喂给 driver——与 learn_da_runner/runner/local_provider.py 的真实
链路一致，最后用带 nonce 的反向扫描解析结果。

判定标准：只要某条 PoC 的 verdict 变成 passed / 断言被判 passed / refs
可读，就说明该越权路径在当前实现下成立（即缺陷存在）。

判定隔离（附录 A.2 两进程拆分）落地后的预期：
- PoC-1/2/2b/3 应当全部「未成立」（被挡住）；
- PoC-4（鸭子类型绕过 expr_true）也应未成立：兼容表达式拒绝自定义对象，
  正式工作区已全部迁移为结构化契约并在后端比较。
"""

from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import sys
import struct
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent            # learn_da_runner/scripts
REPO = HERE.parent.parent                          # 仓库根
RUNNER_DIR = REPO / "learn_da_runner"
DRIVER_SRC = RUNNER_DIR / "runner" / "session_driver.py"
CHILD_SRC = RUNNER_DIR / "runner" / "learner_child.py"
RUNTIME_SRC = REPO / "learn_da" / "app" / "practice" / "assertion_runtime.py"
PYTHON = Path(sys.executable)
MARKER = "__LEARN_DA_SESSION__"

# 一个真实会失败的断言：region_stats 未定义 → expr_true 报 error
FAILING_ASSERTION = {
    "id": "a-rows",
    "type": "expr_true",
    "title": "四个区域",
    "expr": "region_stats.height == 4",
}


def parse_driver_output(stdout_text: str, nonce: str) -> dict | None:
    """与 runner/session.py 相同的 nonce 反向扫描。"""
    for line in reversed(stdout_text.splitlines()):
        if not line.startswith(MARKER):
            continue
        rest = line[len(MARKER):]
        if not rest.startswith(nonce):
            continue  # 伪造行没有本会话的 nonce
        try:
            return json.loads(rest[len(nonce):])
        except json.JSONDecodeError:
            return None
    return None


def run_poc(name: str, cell_code: str, assertions: list[dict], refs: dict | None = None) -> dict | None:
    """按真实链路跑一个 PoC：plan.json 只含格清单，判定材料走 driver stdin。"""
    work = Path(tempfile.mkdtemp(prefix=f"poc_{name}_"))
    try:
        shutil.copy(DRIVER_SRC, work / "driver.py")
        shutil.copy(CHILD_SRC, work / "learner_child.py")
        plan = {
            "cells": [{"cellId": "c1", "code": cell_code, "language": "python"}],
            "stopAt": None,
        }
        (work / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

        nonce = secrets.token_hex(16)
        driver_input = {
            "nonce": nonce,
            "deadlineMs": 20000,
            "assertions": assertions,
            "refs": refs or {},
            "runtime": RUNTIME_SRC.read_text(encoding="utf-8"),
            "child": {
                "specs": [
                    a for a in assertions if a.get("type") in ("expr_true", "sql_rows")
                ],
                "assertionVars": sorted(
                    {
                        a["var"]
                        for a in assertions
                        if a.get("type") in ("frame_equal", "schema") and a.get("var")
                    }
                ),
                "maxVarBytes": 2_000_000,
            },
        }
        data = json.dumps(driver_input, ensure_ascii=False).encode("utf-8")
        proc = subprocess.run(
            [str(PYTHON), "-X", "utf8", "-B", "driver.py"],
            cwd=str(work),
            input=struct.pack("<Q", len(data)) + data,
            capture_output=True,
            timeout=120,
        )
        return parse_driver_output(proc.stdout.decode("utf-8", errors="replace"), nonce)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def verdict_of(payload: dict | None) -> str:
    if not payload:
        return "<no marker>"
    return str(payload.get("verdict"))


def assertion_statuses(payload: dict | None) -> list[str]:
    if not payload:
        return []
    return [str(a.get("status")) for a in (payload.get("assertions") or [])]


def show(title: str, payload: dict | None, expect_forged: bool) -> bool:
    if payload is None:
        print("协议失败：缺少真实 driver 结果，不能当作越权已被阻止")
        return False
    v = verdict_of(payload)
    st = assertion_statuses(payload)
    forged = v == "passed" or any(s == "passed" for s in st)
    mark = "越权成立" if forged else "未成立"
    print(f"  verdict={v!r}  assertions={st}  -> {mark}")
    ok = forged == expect_forged
    print(f"  预期{'越权' if expect_forged else '被挡住'}：{'符合' if ok else '不符合'}")
    return ok


def main() -> int:
    # Windows 控制台默认 GBK，中文会乱码；强制 UTF-8 输出
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for src in (DRIVER_SRC, CHILD_SRC, RUNTIME_SRC):
        if not src.exists():
            print(f"找不到源文件：{src}")
            return 2
    if not PYTHON.exists():
        print(f"找不到 Runner 解释器：{PYTHON}")
        return 2

    results: list[tuple[str, bool]] = []

    print("[PoC-1] atexit 伪造 driver marker（预期：被 nonce 挡住）")
    code1 = (
        "import atexit, json\n"
        "fake = {'cells': [], 'assertions': [{'id': 'a-rows', 'type': 'expr_true', 'title': '四个区域', "
        "'status': 'passed', 'actual': None, 'detail': None, 'durationMs': 0}], "
        "'assertionsSkipped': False, 'executedUpto': 'c1', 'verdict': 'passed', 'durationMs': 1}\n"
        "atexit.register(lambda: print('" + MARKER + "' + json.dumps(fake)))\n"
        "raise ValueError('真实失败')\n"
    )
    results.append(("PoC-1 atexit 伪造 marker", show("PoC-1", run_poc("atexit", code1, [FAILING_ASSERTION]), expect_forged=False)))

    print("[PoC-2] 同进程替换断言运行时（预期：判定在 parent，替换无效）")
    code2 = (
        "import __main__\n"
        "class FakeRuntime:\n"
        "    @staticmethod\n"
        "    def run(namespace, spec, refs=None, **kw):\n"
        "        return [{'id': a.get('id'), 'type': a.get('type'), 'title': a.get('title'), "
        "'status': 'passed', 'actual': None, 'detail': None, 'durationMs': 0} for a in (spec or [])]\n"
        "__main__._load_assertion_runtime = lambda path: FakeRuntime\n"
        "print('runtime 已被替换（只影响学员子进程自己的 __main__）')\n"
    )
    results.append(("PoC-2 替换断言运行时", show("PoC-2", run_poc("runtime", code2, [FAILING_ASSERTION]), expect_forged=False)))

    print("[PoC-2b] frame 爬取判定进程的 plan/refs（预期：refs 不在学员进程任何帧里）")
    code2b = (
        "import sys\n"
        "found = None\n"
        "for depth in range(1, 6):\n"
        "    try:\n"
        "        frame = sys._getframe(depth)\n"
        "    except ValueError:\n"
        "        break\n"
        "    loc = frame.f_locals\n"
        "    if isinstance(loc, dict) and 'plan' in loc and isinstance(loc['plan'], dict):\n"
        "        found = loc['plan']\n"
        "        print('爬到 plan 于深度', depth, '，refs=', sorted((found.get('refs') or {}).keys()))\n"
        "        break\n"
        "if found is None:\n"
        "    print('未爬到 plan')\n"
        "region_stats = None\n"
    )
    payload2b = run_poc("frame_plan", code2b, [FAILING_ASSERTION], refs={"expected/frame_secret.parquet": "UEExAA=="})
    stdout2b = ""
    if payload2b and payload2b.get("cells"):
        stdout2b = payload2b["cells"][0].get("stdout") or ""
    print("  学员格 stdout：")
    for line in stdout2b.splitlines():
        print(f"    {line}")
    leaked2b = "expected/frame_secret.parquet" in stdout2b
    print(f"  -> 通过调用栈 {'拿到' if leaked2b else '未拿到'} refs")
    results.append(("PoC-2b frame 爬取 plan.refs", bool(payload2b and payload2b.get("cells")) and not leaked2b))

    print("[PoC-3] 读 plan.json 拿 refs（预期：plan.json 只含 cells/stopAt，无 refs）")
    secret_ref = {"expected/secret.parquet": "UEExAA=="}
    code3 = (
        "import json\n"
        "plan = json.load(open('plan.json', encoding='utf-8'))\n"
        "print('keys=', sorted(plan.keys()))\n"
        "print('refs=', sorted((plan.get('refs') or {}).keys()))\n"
        "region_stats = None\n"
    )
    payload3 = run_poc("plan_read", code3, [FAILING_ASSERTION], refs=secret_ref)
    cell_stdout = ""
    if payload3 and payload3.get("cells"):
        cell_stdout = payload3["cells"][0].get("stdout") or ""
    leaked = "expected/secret.parquet" in cell_stdout
    print(f"  断言状态={assertion_statuses(payload3)}")
    print("  学员格 stdout：")
    for line in cell_stdout.splitlines():
        print(f"    {line}")
    print(f"  -> refs {'泄漏' if leaked else '未泄漏'}")
    results.append(("PoC-3 plan.json 泄漏 refs", bool(payload3 and payload3.get("cells")) and not leaked))

    print("[PoC-4] 鸭子类型绕过 expr_true（预期：自定义对象被拒绝）")
    code4 = (
        "class Always:\n"
        "    def __getattr__(self, name):\n"
        "        return Always()\n"
        "    def __eq__(self, other):\n"
        "        return True\n"
        "    def __ne__(self, other):\n"
        "        return False\n"
        "    def __hash__(self):\n"
        "        return 0\n"
        "region_stats = Always()\n"
        "print('region_stats 已换成万能相等的假对象')\n"
    )
    results.append(("PoC-4 鸭子类型绕过 expr_true", show("PoC-4", run_poc("ducktype", code4, [FAILING_ASSERTION]), expect_forged=False)))

    print()
    print("=" * 60)
    print("汇总（ok = 符合安全预期；!! = 不符合预期，越权仍在）")
    for name, ok in results:
        print(f"  {'ok ' if ok else '!! '}  {name}")
    blocked = sum(1 for _, ok in results if ok)
    all_ok = all(ok for _, ok in results)
    print(f"\n{blocked}/{len(results)} 项符合安全预期")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
