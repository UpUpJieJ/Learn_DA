"""断言运行时（被内联 / 被打进沙箱镜像的那一份实现）。

这个模块只有一个职责：拿到**学员进程内的命名空间**，按断言定义求值，返回
结构化结果。它不打印、不读盘、不联网，因此既能被服务端直接调用（lint L3/L4、
单测），也能被复制进沙箱镜像后由 ``render_assertion_source`` 生成的小尾巴加载。

两个调用方式（``app/practice/assertions.py`` 负责生成）：

1. **自包含**：把本模块源码 ``exec`` 进一个临时命名空间再调用 :func:`run`，
   适合测试与本地 lint（程序长度不受执行接口 5000 字符上限约束时）。
2. **按路径加载**：沙箱里已经有本文件，尾巴用 ``importlib`` 按绝对路径加载，
   尾巴只有几百字节，能塞进 ``/playground/execute`` 的 5000 字符上限。

依赖策略：只依赖标准库；``polars`` / ``duckdb`` 在真正需要时才 import，
这样没有数据科学依赖的环境也能跑 ``expr_true``。
"""

from __future__ import annotations

import base64
import io
import json
import time
from typing import Any, Callable, Mapping

ACTUAL_LIMIT = 500
PER_ASSERTION_TIMEOUT_MS = 500
TOTAL_BUDGET_MS = 2000

_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "float": float, "int": int, "isinstance": isinstance,
    "len": len, "list": list, "max": max, "min": min, "range": range,
    "round": round, "set": set, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "zip": zip, "None": None, "True": True, "False": False,
}


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def run(
    namespace: Mapping[str, Any],
    spec: list[dict[str, Any]],
    refs: Mapping[str, str] | None = None,
    *,
    actual_limit: int = ACTUAL_LIMIT,
    per_assertion_ms: int = PER_ASSERTION_TIMEOUT_MS,
    total_budget_ms: int = TOTAL_BUDGET_MS,
) -> list[dict[str, Any]]:
    """按顺序求值断言，返回每条断言的结果。

    ``refs`` 是 ``ref 名称 -> base64(参考结果字节)``，由服务端生成并内联。
    """
    encoded_refs = dict(refs or {})
    results: list[dict[str, Any]] = []
    started = time.perf_counter()

    for item in spec:
        entry: dict[str, Any] = {
            "id": item["id"],
            "type": item["type"],
            "title": item.get("title") or "",
            "status": "passed",
            "actual": None,
            "detail": item.get("on_fail"),
            "durationMs": 0,
        }

        elapsed_total = (time.perf_counter() - started) * 1000.0
        if elapsed_total > total_budget_ms:
            entry["status"] = "skipped"
            entry["detail"] = f"超出断言总预算 {total_budget_ms}ms"
            results.append(entry)
            continue

        begin = time.perf_counter()
        try:
            passed, actual = _CHECKS[item["type"]](item, namespace, encoded_refs)
            entry["status"] = "passed" if passed else "failed"
            entry["actual"] = None if passed else _truncate(actual, actual_limit)
            if passed:
                entry["detail"] = None
        except Exception as exc:  # 断言自身出错 ≠ 学员写错，单独标记
            entry["status"] = "error"
            entry["actual"] = _truncate(f"{type(exc).__name__}: {exc}", actual_limit)
            entry["detail"] = None
        duration_ms = (time.perf_counter() - begin) * 1000.0
        entry["durationMs"] = int(duration_ms)
        if entry["status"] in ("passed", "failed") and duration_ms > per_assertion_ms:
            entry["status"] = "timeout"
            entry["detail"] = f"单条断言超过 {per_assertion_ms}ms"
        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _truncate(value: Any, limit: int = ACTUAL_LIMIT) -> str:
    text = value if isinstance(value, str) else repr(value)
    if len(text) > limit:
        return text[:limit] + "...(截断)"
    return text


def _numeric_equal(left: Any, right: Any, rtol: float, atol: float) -> bool:
    try:
        if left == right:
            return True
    except Exception:
        pass
    try:
        return abs(float(left) - float(right)) <= max(atol, rtol * abs(float(right)))
    except (TypeError, ValueError):
        return False


def _cell_equal(left: Any, right: Any, rtol: float, atol: float) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return _numeric_equal(left, right, rtol, atol)
    if isinstance(left, (int, float, str)) and isinstance(right, (int, float, str)):
        if _numeric_equal(left, right, rtol, atol):
            return True
    return left == right


def _table(obj: Any) -> tuple[list[Any] | None, list[list[Any]], dict[str, str] | None]:
    """归一化成 ``(列名, 行, 列类型)``，支持 polars / pandas / 行列表。"""
    if obj is None:
        raise TypeError("变量不存在或为 None")
    if hasattr(obj, "columns") and hasattr(obj, "rows"):  # polars
        return (
            list(obj.columns),
            [list(row) for row in obj.rows()],
            {str(key): str(value) for key, value in obj.schema.items()},
        )
    if hasattr(obj, "columns") and hasattr(obj, "itertuples"):  # pandas
        return (
            list(obj.columns),
            [list(row) for row in obj.itertuples(index=False, name=None)],
            {str(key): str(value) for key, value in obj.dtypes.items()},
        )
    if isinstance(obj, (list, tuple)):
        rows = [list(row) if isinstance(row, (list, tuple)) else [row] for row in obj]
        return None, rows, None
    raise TypeError("不支持的数据类型：" + type(obj).__name__)


def _load_ref(name: str, refs: Mapping[str, str]) -> Any:
    payload = base64.b64decode(refs[name])
    if payload[:4] == b"PAR1":
        import polars as pl

        return pl.read_parquet(io.BytesIO(payload))
    data = json.loads(payload.decode("utf-8"))
    if isinstance(data, dict) and "rows" in data:
        return [list(row) for row in data["rows"]]
    if isinstance(data, list):
        return [list(row) if isinstance(row, (list, tuple)) else [row] for row in data]
    raise TypeError("无法识别的参考结果：" + name)


# ---------------------------------------------------------------------------
# 四型断言
# ---------------------------------------------------------------------------


def _check_expr_true(
    spec: dict[str, Any], namespace: Mapping[str, Any], refs: Mapping[str, str]
) -> tuple[bool, str]:
    expr = spec["expr"]
    value = eval(expr, {"__builtins__": _SAFE_BUILTINS}, dict(namespace))  # noqa: S307
    if value:
        return True, ""
    return False, f"表达式 {expr!r} 为假（实际值：{value!r}）"


def _check_frame_equal(
    spec: dict[str, Any], namespace: Mapping[str, Any], refs: Mapping[str, str]
) -> tuple[bool, str]:
    got_columns, got_rows, _ = _table(namespace.get(spec["var"]))
    ref_columns, ref_rows, _ = _table(_load_ref(spec["ref"], refs))
    rtol, atol = float(spec["rtol"]), float(spec["atol"])

    if got_columns is None:
        got_columns = list(range(len(got_rows[0]) if got_rows else 0))
    if ref_columns is None:
        ref_columns = list(range(len(ref_rows[0]) if ref_rows else 0))
    if len(got_columns) != len(ref_columns):
        return False, f"列数不一致：{list(got_columns)!r} vs {list(ref_columns)!r}"

    positions: list[int] = []
    for column in ref_columns:
        if column not in got_columns:
            return False, f"缺少列 {column!r}（实际列：{list(got_columns)!r}）"
        positions.append(got_columns.index(column))
    if len(positions) != len(got_columns):
        extra = [name for index, name in enumerate(got_columns) if index not in positions]
        return False, f"多余列：{extra!r}（期望列：{list(ref_columns)!r}）"

    rows = [[row[index] for index in positions] for row in got_rows]
    expected = [list(row) for row in ref_rows]
    if len(rows) != len(expected):
        return False, f"行数不一致：{len(rows)} vs {len(expected)}"
    if not spec.get("order_matters", True):
        rows = sorted(rows, key=repr)
        expected = sorted(expected, key=repr)

    for row_index, (row, want) in enumerate(zip(rows, expected)):
        for column_index, (cell, want_cell) in enumerate(zip(row, want)):
            if not _cell_equal(cell, want_cell, rtol, atol):
                return False, (
                    f"第 {row_index} 行 {ref_columns[column_index]!r} 不一致："
                    f"{cell!r} vs {want_cell!r}"
                )
    return True, f"{len(rows)} 行与参考结果一致"


def _check_schema(
    spec: dict[str, Any], namespace: Mapping[str, Any], refs: Mapping[str, str]
) -> tuple[bool, str]:
    columns, _rows, dtypes = _table(namespace.get(spec["var"]))
    if columns is None:
        return False, "变量不含列信息，无法校验 schema"

    wanted_columns = spec.get("columns")
    if wanted_columns is not None:
        if spec.get("exact"):
            if list(columns) != list(wanted_columns):
                return False, (
                    f"列必须完全一致：{list(columns)!r} vs {list(wanted_columns)!r}"
                )
        else:
            missing = [name for name in wanted_columns if name not in columns]
            if missing:
                return False, f"缺少列 {missing!r}（实际列：{list(columns)!r}）"

    wanted_dtypes = spec.get("dtypes") or {}
    if wanted_dtypes:
        if dtypes is None:
            return False, "变量不含类型信息"
        for column, expected in wanted_dtypes.items():
            if column not in dtypes:
                return False, f"缺少列 {column!r}（实际列：{sorted(dtypes)}）"
            if dtypes[column].lower() != str(expected).lower():
                return False, (
                    f"列 {column!r} 类型不一致：{dtypes[column]!r} vs {expected!r}"
                )
    return True, "schema 符合预期"


def _check_sql_rows(
    spec: dict[str, Any], namespace: Mapping[str, Any], refs: Mapping[str, str]
) -> tuple[bool, str]:
    con = namespace.get(spec.get("connection") or "con")
    if con is None or not hasattr(con, "execute"):
        import duckdb

        con = duckdb
    got_rows = [list(row) for row in con.execute(spec["query"]).fetchall()]
    ref_rows = [list(row) for row in _load_ref(spec["ref"], refs)]
    rtol, atol = float(spec["rtol"]), float(spec["atol"])
    if not spec.get("order_matters", False):
        got_rows = sorted(got_rows, key=repr)
        ref_rows = sorted(ref_rows, key=repr)
    if len(got_rows) != len(ref_rows):
        return False, f"行数不一致：{len(got_rows)} vs {len(ref_rows)}"
    for row_index, (row, want) in enumerate(zip(got_rows, ref_rows)):
        for column_index, (cell, want_cell) in enumerate(zip(row, want)):
            if not _cell_equal(cell, want_cell, rtol, atol):
                return False, (
                    f"第 {row_index} 行第 {column_index} 列不一致：{cell!r} vs {want_cell!r}"
                )
    return True, f"{len(got_rows)} 行与参考结果一致"


_CHECKS: dict[str, Callable[[dict[str, Any], Mapping[str, Any], Mapping[str, str]], tuple[bool, str]]] = {
    "expr_true": _check_expr_true,
    "frame_equal": _check_frame_equal,
    "schema": _check_schema,
    "sql_rows": _check_sql_rows,
}