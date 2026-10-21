"""重放式会话执行驱动（在沙箱内运行）。

设计见 ``learn_da/docs/learning-workspace-redesign-2026-10-21.md`` §3.2：

* 一个进程里按顺序 ``exec`` 每个单元格，共享同一个命名空间——所以第 k 格能看到
  前面各格定义的变量，语义上等价于"从头跑到第 k 格"。
* 逐格捕获 stdout / stderr 与耗时；某格抛异常就停下，**后续格标记 skipped**
  （严格顺序：后面依赖前面的状态）。
* 全部格执行完（或执行到 ``stopAt``）后，在**同一个命名空间**里求值断言，
  并把结果与逐格输出一起打成一行 JSON。
* 参考结果（``refs``）由后端以 base64 内联传入，落在本进程内存里，不写到任何
  用户可见路径。

驱动不依赖 Runner 的 venv：只用标准库 + 沙箱里已有的第三方库（polars / duckdb）。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import time
import traceback
from pathlib import Path

MARKER = "__LEARN_DA_SESSION__"
CELL_OUTPUT_LIMIT = 8000
PLAN_FILE = "plan.json"


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= CELL_OUTPUT_LIMIT:
        return text, False
    return text[:CELL_OUTPUT_LIMIT] + "\n…(输出已截断)", True


def _load_assertion_runtime(path: Path):
    spec = importlib.util.spec_from_file_location("_learn_da_assertion_runtime", path)
    if spec is None or spec.loader is None:  # pragma: no cover - 环境损坏
        raise RuntimeError(f"cannot load assertion runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_cell(cell: dict, namespace: dict) -> dict:
    """执行一个单元格，返回逐格结果（失败不抛出）。"""
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    status = "success"
    error_type = None
    started = time.perf_counter()

    try:
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(
            stderr_buffer
        ):
            code = compile(cell["code"], f"<cell:{cell['cellId']}>", "exec")
            exec(code, namespace)  # noqa: S102 - 沙箱内有意执行学员代码
    except SystemExit:
        # 学员代码里调 sys.exit() 不算错误（与 notebook 行为一致）
        status = "success"
    except BaseException as exc:  # noqa: BLE001 - 任何异常都要变成结构化结果
        status = "error"
        error_type = type(exc).__name__
        stderr_buffer.write("".join(traceback.format_exception_only(type(exc), exc)))

    duration_ms = int((time.perf_counter() - started) * 1000)
    stdout_text, stdout_truncated = _clip(stdout_buffer.getvalue())
    stderr_text, stderr_truncated = _clip(stderr_buffer.getvalue())

    return {
        "cellId": cell["cellId"],
        "status": status,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "errorType": error_type,
        "durationMs": duration_ms,
        "truncated": stdout_truncated or stderr_truncated,
    }


def run_plan(plan: dict, root: Path) -> dict:
    """按计划重放单元格并求值断言。"""
    cells = list(plan.get("cells") or [])
    stop_at = plan.get("stopAt")
    namespace: dict = {"__name__": "__main__"}
    results: dict[str, dict] = {}
    reached_end = True
    executed_upto: str | None = None
    started = time.perf_counter()

    for index, cell in enumerate(cells):
        cell_id = cell["cellId"]
        if cell.get("language", "python") == "sql":
            # v1 先把 SQL 单元格当成"未支持"，留出扩展位（详见设计稿 M5）
            results[cell_id] = {
                "cellId": cell_id,
                "status": "error",
                "stdout": "",
                "stderr": "SQL 单元格暂未支持",
                "errorType": "UnsupportedLanguage",
                "durationMs": 0,
                "truncated": False,
            }
            reached_end = False
            break

        result = _run_cell(cell, namespace)
        results[cell_id] = result
        if result["status"] != "success":
            reached_end = False
            break
        if stop_at is not None and cell_id == stop_at:
            executed_upto = cell_id
            break
        if index == len(cells) - 1:
            executed_upto = cell_id

    # 没被执行到的单元格标记 skipped（顺序执行被前面挡住）
    ordered = []
    for cell in cells:
        cell_id = cell["cellId"]
        ordered.append(
            results.get(
                cell_id,
                {
                    "cellId": cell_id,
                    "status": "skipped",
                    "stdout": "",
                    "stderr": "",
                    "errorType": None,
                    "durationMs": 0,
                    "truncated": False,
                },
            )
        )

    assertions: list[dict] = []
    assertions_skipped = False
    spec = plan.get("assertions") or []
    if spec:
        runtime_file = plan.get("runtimeFile")
        if not reached_end or executed_upto is None or not runtime_file:
            # 执行没走完（含被 stopAt 截住的场景之外的失败），或后端没带运行时，
            # 断言都不成立
            assertions_skipped = True
            detail = (
                "缺少断言运行时，未求值"
                if reached_end and executed_upto is not None
                else "前面的单元格未全部执行成功，断言未求值"
            )
            assertions = [
                {
                    "id": item.get("id", f"a{index + 1}"),
                    "type": item.get("type"),
                    "title": item.get("title", ""),
                    "status": "skipped",
                    "actual": None,
                    "detail": detail,
                    "durationMs": 0,
                }
                for index, item in enumerate(spec)
            ]
        else:
            runtime = _load_assertion_runtime(root / runtime_file)
            assertions = runtime.run(namespace, spec, plan.get("refs") or {})

    failed_assertion = next((a for a in assertions if a.get("status") != "passed"), None)
    cell_failed = any(item["status"] == "error" for item in ordered)

    if cell_failed:
        verdict = "execution_failed"
    elif assertions_skipped:
        verdict = "execution_failed"
    elif spec and failed_assertion is not None:
        verdict = "assertion_failed"
    else:
        verdict = "passed"

    return {
        "cells": ordered,
        "assertions": assertions,
        "assertionsSkipped": assertions_skipped,
        "executedUpto": executed_upto,
        "verdict": verdict,
        "durationMs": int((time.perf_counter() - started) * 1000),
    }


def main() -> int:
    root = Path.cwd()
    plan = json.loads((root / PLAN_FILE).read_text(encoding="utf-8"))
    payload = run_plan(plan, root)
    print(MARKER + json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - 沙箱入口
    raise SystemExit(main())