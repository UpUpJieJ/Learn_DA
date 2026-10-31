"""Judge bounded sandbox observations with expectations held only by the API."""
from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.practice.assertion_runtime import run, strict_value
from app.practice.assertions import validate_assertions

MAX_OBSERVATION_BYTES = 2_000_000
_PUBLIC_FIELDS = ("id", "type", "var", "function", "args", "kwargs", "query", "connection")


def observation_request(payload: dict) -> dict:
    outbound = {key: value for key, value in payload.items() if key not in ("refs", "runtime", "assertions")}
    outbound["observationMode"] = True
    outbound["assertions"] = [
        {key: item[key] for key in _PUBLIC_FIELDS if key in item}
        for item in payload.get("assertions", [])
    ]
    return outbound


def _value(payload: Any) -> Any:
    if type(payload) is not dict:
        raise ValueError("未回传变量")
    if payload.get("kind") == "table":
        return _Table(payload)
    data = payload.get("data")
    if not isinstance(data, str) or len(data.encode("utf-8")) > MAX_OBSERVATION_BYTES:
        raise ValueError("变量缺失或超出回传上限")
    if payload.get("kind") == "json":
        return strict_value(json.loads(data))
    raise ValueError("不支持的变量类型")


def _cell(value):
    if type(value) is not dict:
        return strict_value(value)
    if len(value) != 1:
        raise ValueError("不支持的表格单元格")
    if "__d__" in value:
        return date.fromisoformat(value["__d__"])
    if "__dt__" in value:
        return datetime.fromisoformat(value["__dt__"])
    if "__dec__" in value:
        number = Decimal(value["__dec__"])
        if not number.is_finite():
            raise ValueError("非有限小数")
        return number
    if "__b64__" in value:
        return base64.b64decode(value["__b64__"], validate=True)
    if "__float__" in value and value["__float__"] in ("nan", "inf", "-inf"):
        return float(value["__float__"])
    raise ValueError("不支持的表格单元格标签")


class _Table:
    def __init__(self, payload):
        columns, rows, dtypes = payload.get("columns"), payload.get("rows"), payload.get("dtypes")
        if (type(columns) is not list or not all(type(c) is str for c in columns)
                or len(set(columns)) != len(columns) or type(rows) is not list
                or type(dtypes) is not dict or set(dtypes) != set(columns)
                or not all(type(v) is str for v in dtypes.values())):
            raise ValueError("表格列定义不合法")
        if not all(type(row) is list and len(row) == len(columns) for row in rows):
            raise ValueError("表格行宽与列数不一致")
        self.columns, self.schema = columns, dtypes
        self._rows = [[_cell(v) for v in row] for row in rows]
        for index, name in enumerate(columns):
            check = _dtype_check(dtypes[name])
            if not all(value is None or check(value) for value in (row[index] for row in self._rows)):
                raise ValueError(f"列 {name!r} 的实际值不符合类型 {dtypes[name]}")

    def rows(self):
        return self._rows


def _dtype_check(dtype):
    """Validate data against a small explicit wire type set, never eval metadata."""
    if dtype == "Float32":
        import math
        import struct
        def check_float32(value):
            if type(value) is not float:
                return False
            if not math.isfinite(value):
                return True
            try:
                return struct.unpack("f", struct.pack("f", value))[0] == value
            except (OverflowError, struct.error):
                return False
        return check_float32
    primitive = {"String": str, "Utf8": str, "Boolean": bool, "Binary": bytes,
                 "Float64": float, "Date": date, "Null": type(None)}
    if dtype in primitive:
        return lambda value: type(value) is primitive[dtype]
    integer = re.fullmatch(r"(U?Int)(8|16|32|64|128)", dtype)
    if integer:
        bits = int(integer[2])
        lower = 0 if integer[1].startswith("U") else -(2 ** (bits - 1))
        upper = 2 ** bits - 1 if lower == 0 else 2 ** (bits - 1) - 1
        return lambda value: type(value) is int and lower <= value <= upper
    dt = re.fullmatch(r"Datetime\(time_unit='(?:ms|us|ns)', time_zone=(None|'[^']{1,100}')\)", dtype)
    if dt:
        return lambda value: type(value) is datetime and ((value.tzinfo is None) == (dt[1] == "None"))
    dec = re.fullmatch(r"Decimal\(precision=(None|\d{1,2}), scale=(\d{1,2})\)", dtype)
    if dec:
        precision, scale = (38 if dec[1] == "None" else int(dec[1])), int(dec[2])
        if not 0 <= scale <= precision <= 38:
            raise ValueError("不支持的小数类型")
        def check_decimal(value):
            if type(value) is not Decimal:
                return False
            if value.is_zero():
                return True
            digits = value.as_tuple().digits
            shift = value.as_tuple().exponent + scale
            if shift < 0 and (-shift > len(digits) or any(digits[shift:])):
                return False
            return len(digits) + shift <= precision
        return check_decimal
    raise ValueError("不支持的表格类型：" + dtype)


def _sql_plain(value):
    value = _cell(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


class _Cursor:
    def __init__(self, rows, columns=None):
        self._rows = rows
        self.description = [(c,) for c in columns] if columns is not None else None

    def execute(self, query):
        return self

    def fetchall(self):
        return self._rows


def _entry(spec: dict, status: str, message: str) -> dict:
    return dict(id=spec["id"], type=spec["type"], title=spec.get("title", ""),
                status=status, actual=message[:500] if status != "skipped" else None,
                detail=message if status == "skipped" else None, durationMs=0)


def judge_observations(request: dict, result: dict) -> dict:
    """Ignore sandbox verdicts. Only concrete observations can satisfy a contract."""
    specs = validate_assertions(request.get("assertions", []))
    judged = dict(result)
    events = judged.pop("observations", [])
    expected = []
    for cell in request.get("cells", []):
        expected.append(cell["cellId"])
        if cell["cellId"] == request.get("stopAt"):
            break
    cells = result.get("cells", [])
    requested_ids = [cell["cellId"] for cell in request.get("cells", [])]
    valid_cells = (type(cells) is list and all(type(c) is dict for c in cells)
                   and [c.get("cellId") for c in cells] == requested_ids
                   and len(set(requested_ids)) == len(requested_ids)
                   and all(c.get("status") == ("success" if c["cellId"] in expected else "skipped") for c in cells))
    execution_ok = (result.get("status") == "success" and bool(expected)
                    and valid_cells
                    and result.get("executedUpto") == expected[-1]
                    and not result.get("error"))
    assertions = []
    if not execution_ok:
        assertions = [_entry(s, "skipped", "前面的单元格未全部执行成功，断言未求值") for s in specs]
    else:
        if not isinstance(events, list) or len(json.dumps(events, ensure_ascii=False).encode()) > MAX_OBSERVATION_BYTES:
            events = []
        variables, calls, queries = {}, {}, {}
        duplicate = False
        for event in events:
            if not isinstance(event, dict):
                continue
            kind = event.get("t")
            if kind == "vars" and isinstance(event.get("vars"), dict):
                duplicate |= bool(variables.keys() & event["vars"].keys())
                variables.update(event["vars"])
            elif kind in ("call", "rows") and isinstance(event.get("id"), str):
                target = calls if kind == "call" else queries
                duplicate |= event["id"] in target
                target[event["id"]] = event
        for spec in specs:
            try:
                if duplicate:
                    raise ValueError("观察结果重复")
                kind = spec["type"]
                if kind == "expr_true":
                    raise ValueError("工作区不再接受自由表达式断言，请迁移为结构化断言")
                if kind == "call":
                    event = calls.get(spec["id"], {})
                    if event.get("error"):
                        raise ValueError(event["error"])
                    value = _value(event.get("value"))
                    item = run({"result": value}, [dict(spec, type="value", var="result")])[0]
                    item["type"] = "call"
                elif kind == "sql_rows":
                    event = queries.get(spec["id"], {})
                    if event.get("error") or type(event.get("rows")) is not list:
                        raise ValueError(event.get("error") or "未回传 SQL 查询结果")
                    if not all(type(row) is list for row in event["rows"]):
                        raise ValueError("SQL 行必须为列表")
                    rows = [[_sql_plain(cell) for cell in row] for row in strict_value(event["rows"])]
                    columns = event.get("columns")
                    if columns is not None and (type(columns) is not list or not all(type(c) is str for c in columns)
                                                or len(set(columns)) != len(columns)
                                                or not all(len(row) == len(columns) for row in rows)):
                        raise ValueError("SQL 列定义不合法")
                    item = run({spec.get("connection", "con"): _Cursor(rows, columns)}, [spec], request.get("refs"))[0]
                else:
                    value = _value(variables.get(spec.get("var")))
                    item = run({spec["var"]: value}, [spec], request.get("refs"))[0]
                assertions.append(item)
            except Exception as exc:
                assertions.append(_entry(spec, "error", f"{type(exc).__name__}: {exc}"))
    judged["assertions"] = assertions
    judged["assertionsSkipped"] = not execution_ok and bool(specs)
    judged["verdict"] = ("execution_failed" if not execution_ok else
                         "assertion_failed" if any(a["status"] != "passed" for a in assertions) else "passed")
    return judged
