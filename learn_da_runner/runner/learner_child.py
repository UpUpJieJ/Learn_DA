"""学员代码执行子进程（在沙箱内由 parent ``driver.py`` 拉起）。

与 parent（``runner/session_driver.py``，复制为 ``driver.py``）的分工
（refactor-review-2026-10-26.md 附录 A.2 的落地）：

* 本进程按顺序 ``exec`` 学员单元格，共享命名空间，逐格捕获输出——一切学员
  代码只在本进程里运行，**parent 从不执行学员代码**。
* 判定（frame_equal / schema 的比对、sql_rows 的比对、refs）发生在 parent
  内存里：``refs`` 只经 stdin 进入 parent，**永远不进入本进程**。
* 本进程从 stdin 收到 ``{specs, runtime, assertionVars, maxVarBytes}``：
  ``specs`` 只含 expr_true / sql_rows（必须接触学员命名空间里的对象才能求值
  / 取数），``runtime`` 是断言运行时源码（仓库内公开文件，非机密），没有
  refs。``plan.json`` 只剩 ``{cells, stopAt}``——学员读它只能看到自己的格清单。

回传协议：每个事件一行 ``__LEARN_DA_CHILD__`` + JSON，写到本进程 stdout。
这是与 parent 之间的独立管道：学员格的 print 被逐格重定向捕获，``atexit``
钩子也只在本进程退出时跑，都碰不到 parent 的 stdout。

安全模型：本进程回传的一切（cells 状态 / expr 结果 / 序列化变量 / SQL 行）
在 parent 一律按**不可信数据**处理——伪造它们伪造不出「通过」：
frame_equal / schema / sql_rows 的比对在 parent 用 parent 独有的 refs 做，
伪造变量值必须与 refs 逐行一致才可能通过；expr_true 在过渡期
（P0-6：内容迁移 + 类型契约修复前）本来就承认为不可信。
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import time
import traceback
from pathlib import Path

CHILD_MARKER = "__LEARN_DA_CHILD__"
CELL_OUTPUT_LIMIT = 8000
PLAN_FILE = "plan.json"


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= CELL_OUTPUT_LIMIT:
        return text, False
    return text[:CELL_OUTPUT_LIMIT] + "\n…(输出已截断)", True


def _emit(event: dict) -> None:
    # 用 __stdout__（管道本体）：学员代码可能替换过 sys.stdout。
    stream = sys.__stdout__
    stream.write(CHILD_MARKER + json.dumps(event, ensure_ascii=False) + "\n")
    stream.flush()


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


def _load_runtime(source: str):
    """把断言运行时源码 exec 进全新命名空间，不落盘。

    盘上的文件在加载前可能被学员格改写，所以只认 stdin 传来的源码。
    """
    import types

    module = types.ModuleType("_learn_da_assertion_runtime")
    exec(compile(source, "<assertion_runtime>", "exec"), module.__dict__)
    return module


def _fetch_sql_rows(spec: dict, namespace: dict) -> list:
    """跑 sql_rows 的查询，返回原始行（比对在 parent 做）。

    连接查找顺序与断言运行时一致：命名空间里的 ``con``（或 spec 指定的
    连接名）→ 兜底模块级 duckdb（学员 ``import duckdb`` 后建过表也能查到）。
    """
    con = namespace.get(spec.get("connection") or "con")
    if con is None or not hasattr(con, "execute"):
        import duckdb

        con = duckdb
    cursor = con.execute(spec["query"])
    return [str(item[0]) for item in cursor.description or []], cursor.fetchall()


def _jsonify_cell(value):
    """SQL 结果单元格的可序列化表示（parent 侧会按 tag 还原）。"""
    import base64
    import datetime
    import decimal
    import math

    if type(value) is float and not math.isfinite(value):
        return {"__float__": "nan" if math.isnan(value) else "inf" if value > 0 else "-inf"}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime.datetime):
        return {"__dt__": value.isoformat()}
    if isinstance(value, datetime.date):
        return {"__d__": value.isoformat()}
    if isinstance(value, decimal.Decimal):
        return {"__dec__": str(value)}
    if isinstance(value, (bytes, bytearray)):
        return {"__b64__": base64.b64encode(bytes(value)).decode("ascii")}
    return {"__repr__": repr(value), "typeName": type(value).__name__}


def _serialize_var(value, max_bytes: int) -> dict:
    """把一个断言变量序列化回 parent。

    polars 表（与运行时 ``_table`` 的鸭子检查同口径：columns + rows）走
    有界 JSON 表；原生 JSON 值直接走 JSON；其余标记为 unsupported，parent
    会重建一个类型名相同的占位对象，让运行时报错文案保持原样。
    """
    if value is None:
        return {"kind": "json", "data": "null"}
    if hasattr(value, "columns") and hasattr(value, "rows"):
        try:
            table = {"kind": "table", "columns": list(value.columns),
                     "rows": [[_jsonify_cell(cell) for cell in row] for row in value.rows()],
                     "dtypes": {str(k): str(v) for k, v in value.schema.items()}}
            if len(json.dumps(table, ensure_ascii=False).encode("utf-8")) > max_bytes:
                return {
                    "kind": "unsupported",
                    "typeName": type(value).__name__,
                    "reason": f"序列化结果超过 {max_bytes} 字节上限",
                }
            return table
        except Exception:  # noqa: BLE001 - 非法表格对象降级为 unsupported
            return {"kind": "unsupported", "typeName": type(value).__name__}
    try:
        _strict_json(value)
        return {"kind": "json", "data": json.dumps(value, ensure_ascii=False)}
    except (TypeError, ValueError):
        return {"kind": "unsupported", "typeName": type(value).__name__}


def _strict_json(value, depth=0):
    import math
    if depth > 30:
        raise ValueError("值嵌套过深")
    kind = type(value)
    if value is None or kind in (bool, int, str):
        return
    if kind is float and math.isfinite(value):
        return
    if kind is list:
        for item in value:
            _strict_json(item, depth + 1)
        return
    if kind is dict and all(type(key) is str for key in value):
        for item in value.values():
            _strict_json(item, depth + 1)
        return
    raise TypeError("需要 JSON 原生类型")


def main() -> int:
    root = Path.cwd()
    plan = json.loads((root / PLAN_FILE).read_text(encoding="utf-8"))
    child_input = json.loads(sys.stdin.read() or "{}")
    specs = [s for s in (child_input.get("specs") or []) if isinstance(s, dict)]
    runtime_source = child_input.get("runtime")
    var_names = [n for n in (child_input.get("assertionVars") or []) if isinstance(n, str)]
    max_var_bytes = int(child_input.get("maxVarBytes") or 2_000_000)

    cells = list(plan.get("cells") or [])
    stop_at = plan.get("stopAt")
    namespace: dict = {"__name__": "__main__"}
    results: dict[str, dict] = {}
    reached_end = True
    executed_upto: str | None = None

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

    _emit(
        {
            "t": "done",
            "cells": ordered,
            "executedUpto": executed_upto,
            "reachedEnd": reached_end,
        }
    )

    # 回传条件与旧 driver 的求值条件一致：执行走完才求值。变量序列化不依赖
    # expr/sql specs（frame_equal-only 的会话也要回传变量），只依赖执行状态。
    if not reached_end or executed_upto is None:
        return 0

    expr_specs = [s for s in specs if s.get("type") == "expr_true"]
    sql_specs = [s for s in specs if s.get("type") == "sql_rows"]

    if expr_specs and runtime_source:
        try:
            runtime = _load_runtime(runtime_source)
            items = runtime.run(namespace, expr_specs, None)
            _emit({"t": "assertions", "items": items})
        except Exception as exc:  # noqa: BLE001 - 加载失败逐条上报
            message = f"断言运行时加载失败：{type(exc).__name__}: {exc}"
            _emit(
                {
                    "t": "assertions",
                    "items": [
                        {
                            "id": spec.get("id"),
                            "type": spec.get("type"),
                            "title": spec.get("title") or "",
                            "status": "error",
                            "actual": message[:500],
                            "detail": None,
                            "durationMs": 0,
                        }
                        for spec in expr_specs
                    ],
                }
            )

    for spec in sql_specs:
        try:
            columns, rows = _fetch_sql_rows(spec, namespace)
            _emit(
                {
                    "t": "rows",
                    "id": spec.get("id"),
                    "columns": columns,
                    "rows": [[_jsonify_cell(cell) for cell in row] for row in rows],
                }
            )
        except Exception as exc:  # noqa: BLE001 - 查询失败按事件上报
            _emit({"t": "rows", "id": spec.get("id"), "error": f"{type(exc).__name__}: {exc}"})

    for spec in (s for s in specs if s.get("type") == "call"):
        try:
            from types import FunctionType
            function = namespace.get(spec.get("function"))
            if type(function) is not FunctionType:
                raise TypeError("需要使用 def 定义函数")
            value = function(*spec.get("args", []), **spec.get("kwargs", {}))
            _emit({"t": "call", "id": spec["id"], "value": _serialize_var(value, max_var_bytes)})
        except Exception as exc:
            _emit({"t": "call", "id": spec["id"], "error": f"{type(exc).__name__}: {exc}"})

    if var_names:
        vars_out = {}
        for name in var_names:
            if name in namespace:
                vars_out[name] = _serialize_var(namespace[name], max_var_bytes)
            else:
                vars_out[name] = {"kind": "missing"}
        _emit({"t": "vars", "vars": vars_out})

    return 0


if __name__ == "__main__":  # pragma: no cover - 沙箱入口
    sys.exit(main())
