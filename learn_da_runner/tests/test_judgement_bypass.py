"""判定越权回归测试（报告 refactor-review-2026-10-26.md 附录 A 的五条 PoC）。

这些测试驱动**真实的** execute_session 链路（prepare_workspace → driver
parent 子进程 → learner_child 子进程 → 反向扫描 marker+nonce 行），断言的
是**安全侧的期望行为**：学员代码不能伪造判定结论、不能触达参考结果
（refs）。

判定隔离（附录 A.2，两进程拆分）落地后的状态：

- PoC-1 / PoC-2 / PoC-2b / PoC-3 已修复：判定在 parent 进程内做，refs 经
  stdin 进 parent 内存、不落盘、不进学员进程；marker 行带 nonce，伪造行
  过不了解析。这四条现在是**常绿的回归护栏**；
- PoC-4（鸭子类型绕过 expr_true）仍标记 xfail：expr_true 过渡期在学员
  子进程内求值（需要学员命名空间里的对象），承认为不可信，要等类型契约
  （P0-6 / 附录 A.3 第 2 步）落地后才删。

测试刻意只用 JSON refs 与纯 stdlib 学员代码（不 import polars），
保证 runner venv 也能跑完整链路。
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

from runner.local_provider import LocalSubprocessProvider
from runner.schemas import RunnerSessionRequest, SessionCell

RUNTIME_PATH = (
    Path(__file__).resolve().parents[2]
    / "learn_da"
    / "app"
    / "practice"
    / "assertion_runtime.py"
)

MARKER = "__LEARN_DA_SESSION__"
SECRET_REF = "expected/secret.parquet"

# 一个永远不会被解码的 ref 值（没有断言引用它，只用于验证「泄漏」本身）
SECRET_REF_B64 = base64.b64encode(b"not-a-real-parquet-payload").decode("ascii")

# 与 scripts/poc_judgement_bypass.py 同源的 expr 断言（PoC-4 场景）
_EXPR_ASSERTION = {
    "id": "a-rows",
    "type": "expr_true",
    "title": "四个区域",
    "expr": "region_stats.height == 4",
}


def _provider() -> LocalSubprocessProvider:
    return LocalSubprocessProvider(
        python_executable=sys.executable, timeout_seconds=30
    )


def _cell(cell_id: str, code: str) -> SessionCell:
    return SessionCell(cellId=cell_id, code=code)


def _request(
    cells: list[SessionCell],
    assertions: list[dict],
    refs: dict[str, str] | None = None,
) -> RunnerSessionRequest:
    runtime = RUNTIME_PATH.read_text(encoding="utf-8") if RUNTIME_PATH.exists() else ""
    return RunnerSessionRequest(
        requestId="22222222-2222-2222-2222-222222222222",
        cells=cells,
        datasets={},
        runtime=runtime,
        refs=refs or {},
        assertions=assertions,
    )


def _cell_stdout(result: dict, index: int = 0) -> str:
    cells = result.get("cells") or []
    if index >= len(cells):
        return ""
    return (cells[index].get("stdout") or "") + "\n" + (cells[index].get("stderr") or "")


# ---------------------------------------------------------------------------
# PoC-1：atexit 补打伪造 marker 行，反向扫描会取到它（P0-3）
# 已修复：marker 行带 nonce（Runner 生成、经 stdin 进 parent），伪造行
# 没有 nonce，直接跳过；且 atexit 只能打到学员子进程自己的 stdout 管道。
# ---------------------------------------------------------------------------
def test_poc1_atexit_marker_cannot_forge_verdict() -> None:
    fake_payload = {
        "cells": [],
        "assertions": [
            {
                "id": "a-rows",
                "type": "expr_true",
                "title": "四个区域",
                "status": "passed",
                "actual": None,
                "detail": None,
                "durationMs": 0,
            }
        ],
        "assertionsSkipped": False,
        "executedUpto": "c1",
        "verdict": "passed",
        "durationMs": 1,
    }
    code = (
        "import atexit, json\n"
        f"fake = {fake_payload!r}\n"
        f"atexit.register(lambda: print({MARKER!r} + json.dumps(fake)))\n"
        "raise ValueError('真实失败')\n"
    )
    result = _provider().execute_session(
        _request([_cell("c1", code)], [_EXPR_ASSERTION])
    )

    # 伪造 marker 不得把「真实失败」的会话变成 passed（断言顺序：verdict 必须最先，
    # 伪造 payload 的 cells=[] 会让下标访问在坏实现上先崩掉）
    assert result["verdict"] != "passed", "atexit 伪造的 marker 让失败会话变成了 passed"
    # 真实执行结果必须仍然可见
    assert (result["cells"] or [{}])[0].get("errorType") == "ValueError"


# ---------------------------------------------------------------------------
# PoC-2：学员格替换 __main__._load_assertion_runtime 后 frame_equal 也被判通过（P0-2）
# 已修复：frame_equal / schema 的判定在 parent 进程内做（parent 用 stdin 源码
# 加载运行时、refs 只在 parent 内存），学员进程里替换运行时不再影响判定。
# ---------------------------------------------------------------------------
def test_poc2_runtime_replacement_cannot_forge_frame_equal() -> None:
    ref_value = base64.b64encode(
        json.dumps({"rows": [["华东", 30], ["华北", 40]]}, ensure_ascii=False).encode(
            "utf-8"
        )
    ).decode("ascii")
    frame_spec = {
        "id": "a-frame",
        "type": "frame_equal",
        "title": "区域统计与参考结果逐行一致",
        "var": "region_stats",
        "ref": "expected/region_stats.json",
        "rtol": 1e-6,
        "atol": 0.0,
    }
    code = (
        "import __main__\n"
        "class FakeRuntime:\n"
        "    @staticmethod\n"
        "    def run(namespace, specs, refs=None, **kwargs):\n"
        "        return [{'id': a.get('id'), 'type': a.get('type'), "
        "'title': a.get('title'), 'status': 'passed', 'actual': None, "
        "'detail': None, 'durationMs': 0} for a in (specs or [])]\n"
        "__main__._load_assertion_runtime = lambda path: FakeRuntime\n"
        "region_stats = [['华东', 31], ['华北', 40]]  # 31 是错的，参考值是 30\n"
        "print('runtime 已被替换')\n"
    )
    result = _provider().execute_session(
        _request(
            [_cell("c1", code)],
            [frame_spec],
            refs={"expected/region_stats.json": ref_value},
        )
    )

    assert result["verdict"] != "passed", "替换断言运行时后错误的 frame_equal 被判通过"
    assert (result["assertions"] or [{}])[0].get("status") != "passed"


# ---------------------------------------------------------------------------
# PoC-2b：从学员格的调用栈向上爬，读判定进程帧里的 plan.refs（P0-1）
# 已修复：refs 不再出现在学员进程任何帧里（判定材料走 parent stdin，
# plan.json 只含 cells/stopAt）。
# ---------------------------------------------------------------------------
def test_poc2b_frame_crawl_cannot_reach_refs() -> None:
    code = (
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
    result = _provider().execute_session(
        _request([_cell("c1", code)], [_EXPR_ASSERTION], refs={SECRET_REF: SECRET_REF_B64})
    )

    stdout = _cell_stdout(result)
    assert SECRET_REF not in stdout, "学员格从调用栈爬到了 refs 名称"


# ---------------------------------------------------------------------------
# PoC-3：plan.json 落盘含 refs，学员格直接读文件（P0-1）
# 已修复：plan.json 只含 {cells, stopAt}——学员可读但无秘密；refs 经
# driver stdin 进 parent 内存，永不落盘。
# ---------------------------------------------------------------------------
def test_poc3_plan_json_does_not_leak_refs() -> None:
    code = (
        "import json\n"
        "plan = json.load(open('plan.json', encoding='utf-8'))\n"
        "print('keys=', sorted(plan.keys()))\n"
        "print('refs=', sorted((plan.get('refs') or {}).keys()))\n"
        "region_stats = None\n"
    )
    result = _provider().execute_session(
        _request([_cell("c1", code)], [_EXPR_ASSERTION], refs={SECRET_REF: SECRET_REF_B64})
    )

    stdout = _cell_stdout(result)
    assert SECRET_REF not in stdout, "plan.json 泄漏了 refs 名称"
    # 修复不能靠删掉 plan.json：格清单仍然要在（child 需要它拿 cells/stopAt）
    assert "cells" in stdout and "stopAt" in stdout, "plan.json 丢了格清单"


# ---------------------------------------------------------------------------
# PoC-4：鸭子类型万能相等对象绕过 expr_true（P0-6，等类型契约落地后才修）
# ---------------------------------------------------------------------------
def test_poc4_duck_type_cannot_pass_expr_true() -> None:
    code = (
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
        "print('已换成万能相等的假对象')\n"
    )
    result = _provider().execute_session(
        _request([_cell("c1", code)], [_EXPR_ASSERTION])
    )

    assert result["verdict"] != "passed", "鸭子类型假对象骗过了 expr_true"
    assert (result["assertions"] or [{}])[0].get("status") != "passed"
