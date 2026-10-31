"""会话驱动 parent 进程（在沙箱内运行，复制为 work/driver.py）。

正式工作区使用 observationMode：仅收集有界 JSON 观察结果，refs/expect 不进入
容器，可信比较在 API 后端。下述进程内判定仅为旧内部脚本保留。

判定与执行分离（refactor-review-2026-10-26.md 附录 A.2 的落地）：

* 本进程**不执行任何学员代码**。它从 stdin 读入判定材料（断言定义、refs、
  断言运行时源码、nonce、会话期限），拉起 ``learner_child.py`` 执行学员格，
  然后把子进程回传的**不可信数据**与 parent 独有的 refs 在本进程内存里做
  受信任判定：
  - ``frame_equal`` / ``schema``：parent 重建学员变量（JSON 表 / JSON 值）
    后用真运行时求值；
  - ``sql_rows``：子进程回传查询行，比对在 parent；
  - ``expr_true``：子进程求值（需要学员命名空间里的对象），过渡期承认为
    不可信（P0-6：内容迁移 + 类型契约修复前）。
* ``refs`` 只经 stdin 进入本进程内存，**不落盘、不进子进程**——学员格读
  ``plan.json`` 只能看到格清单；帧栈爬取爬不到 parent 的局部变量；子进程的
  ``atexit`` / print 只能写到子进程自己的 stdout 管道，碰不到本进程的输出。
* 本进程 stdout 只有一行 ``MARKER + nonce + JSON``。nonce 由 Runner 生成、
  经 stdin 传入——伪造 marker 行没有 nonce，解析端直接跳过。

超时由本进程自管（deadline 从 stdin 传入，比 provider 的会话期限留出余量）：
学员格死循环时本进程先杀子进程再输出 execution_failed 结果，避免 provider
杀掉本进程后留下孤儿子进程锁住临时目录。
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

MARKER = "__LEARN_DA_SESSION__"
CHILD_FILENAME = "learner_child.py"
CHILD_MARKER = "__LEARN_DA_CHILD__"
READ_CHUNK = 65536
MAX_CHILD_STDERR_BYTES = 65_536
MAX_CHILD_ERROR_CHARS = 500
RESULT_MAX_BYTES_DEFAULT = 2_000_000
DEADLINE_MARGIN_SECONDS = 1.5

# type tags 与 learner_child._jsonify_cell 一一对应
_CELL_TAGS = ("__dt__", "__d__", "__dec__", "__b64__", "__repr__")


def _load_runtime(source: str):
    """把断言运行时源码 exec 进全新命名空间，不落盘。

    盘上的文件在加载前可能被学员格改写（本进程与学员同用户同 fs），所以
    只认 stdin 传来的源码。
    """
    import types

    module = types.ModuleType("_learn_da_assertion_runtime")
    exec(compile(source, "<assertion_runtime>", "exec"), module.__dict__)
    return module


class _RowsResult:
    """duckdb ``execute().fetchall()`` 结果的最小仿真。"""

    __slots__ = ("_rows",)

    def __init__(self, rows: list[list[Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[list[Any]]:
        return self._rows


class _FakeConnection:
    """喂给断言运行时的只读连接：查询结果已由子进程取回。"""

    __slots__ = ("_rows",)

    def __init__(self, rows: list[list[Any]]) -> None:
        self._rows = [list(row) for row in rows]

    def execute(self, _query: str) -> _RowsResult:
        return _RowsResult(self._rows)


def _make_unsupported(type_name: str) -> Any:
    """重建一个「类型名相同」的占位对象，让运行时报错文案保持原样。"""
    return type(str(type_name), (), {})()


def _reconstruct_cell(value: Any) -> Any:
    if isinstance(value, dict):
        if "__dt__" in value:
            return datetime.fromisoformat(value["__dt__"])
        if "__d__" in value:
            return date.fromisoformat(value["__d__"])
        if "__dec__" in value:
            return Decimal(value["__dec__"])
        if "__b64__" in value:
            return base64.b64decode(value["__b64__"])
        if "__float__" in value and value["__float__"] in ("nan", "inf", "-inf"):
            return float(value["__float__"])
        if "__repr__" in value:
            # 无法重建的值：给占位对象，确保比较失败而不是误判相等
            return _make_unsupported(value.get("typeName") or "unknown")
    return value


def _reconstruct_var(payload: Any) -> Any:
    """把子进程回传的变量表示重建成本地对象（不可信数据）。"""
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    if kind == "table":
        value = type("ObservedTable", (), {})()
        value.columns = payload["columns"]
        value.schema = payload["dtypes"]
        rows = [[_reconstruct_cell(c) for c in row] for row in payload["rows"]]
        value.rows = lambda: rows
        return value
    if kind == "arrow":
        import polars as pl  # 惰性 import：只有表格断言才需要

        return pl.read_ipc(io.BytesIO(base64.b64decode(payload.get("data") or "")))
    if kind == "json":
        return json.loads(payload.get("data") or "null")
    if kind == "missing":
        return None
    return _make_unsupported(payload.get("typeName") or "unknown")


def _drain(stream, into: list, max_bytes: int | None = None) -> None:
    """后台线程读取子进程输出，避免子进程写满管道造成死锁。"""
    total = 0
    try:
        while True:
            chunk = stream.read(READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            into.append(chunk)
            if max_bytes is not None and total > max_bytes:
                into.append(None)  # 哨兵：超出上限
                break
    except Exception:  # noqa: BLE001 - 读取失败按已读内容处理
        pass


def _run_child(
    root: Path, child_payload: bytes, deadline_seconds: float, max_bytes: int
) -> tuple[bytes, str, bool, int | None, bool]:
    """拉起学员子进程并收回全部事件。

    返回 ``(child_stdout, child_stderr, timed_out, exit_code, oversized)``。
    """
    child = subprocess.Popen(
        [sys.executable, "-I", "-X", "utf8", "-B", CHILD_FILENAME],
        cwd=str(root),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out: list = []
    err: list = []
    out_thread = threading.Thread(
        target=_drain, args=(child.stdout, out, max_bytes), daemon=True
    )
    err_thread = threading.Thread(
        target=_drain, args=(child.stderr, err, MAX_CHILD_STDERR_BYTES), daemon=True
    )
    out_thread.start()
    err_thread.start()

    timed_out = False
    try:
        try:
            child.stdin.write(child_payload)
            child.stdin.close()
        except (BrokenPipeError, OSError):
            pass  # 子进程早夭：wait() 会以非零退出码暴露
        try:
            child.wait(timeout=max(0.5, deadline_seconds))
        except subprocess.TimeoutExpired:
            timed_out = True
    finally:
        if child.poll() is None:
            child.kill()
            try:
                child.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        for pipe in (child.stdin, child.stdout, child.stderr):
            try:
                if pipe is not None and not pipe.closed:
                    pipe.close()
            except Exception:  # noqa: BLE001
                pass
        out_thread.join(timeout=5)
        err_thread.join(timeout=5)

    oversized = bool(out) and out[-1] is None
    if oversized:
        out.pop()
    raw_stdout = b"".join(chunk for chunk in out if chunk is not None)
    raw_stderr = b"".join(chunk for chunk in err if chunk is not None)
    child_stderr = raw_stderr.decode("utf-8", errors="replace")
    return raw_stdout, child_stderr, timed_out, child.returncode, oversized


def _parse_events(raw: bytes) -> list[dict]:
    events: list[dict] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.startswith(CHILD_MARKER):
            continue
        try:
            events.append(json.loads(line[len(CHILD_MARKER) :]))
        except json.JSONDecodeError:
            continue
    return events


def _error_item(spec: dict, message: str) -> dict:
    return {
        "id": spec.get("id"),
        "type": spec.get("type"),
        "title": spec.get("title") or "",
        "status": "error",
        "actual": message[:500],
        "detail": None,
        "durationMs": 0,
    }


def _judge_sql(spec: dict, rows_event: Any, runtime, refs: dict) -> dict:
    if not isinstance(rows_event, dict):
        return _error_item(spec, "学员进程未回传 SQL 查询结果")
    if rows_event.get("error"):
        return _error_item(spec, str(rows_event["error"]))
    rows = [
        [_reconstruct_cell(cell) for cell in row]
        for row in (rows_event.get("rows") or [])
    ]
    conn_key = spec.get("connection") or "con"
    namespace = {conn_key: _FakeConnection(rows)}
    try:
        return runtime.run(namespace, [spec], refs)[0]
    except Exception as exc:  # noqa: BLE001 - 畸形 spec / 运行时加载失败
        return _error_item(spec, f"{type(exc).__name__}: {exc}")


def _judge_frame(spec: dict, value: Any, runtime, refs: dict) -> dict:
    namespace = {spec.get("var"): value}
    try:
        return runtime.run(namespace, [spec], refs)[0]
    except Exception as exc:  # noqa: BLE001 - 畸形 spec / 运行时加载失败
        return _error_item(spec, f"{type(exc).__name__}: {exc}")


def _build_payload(
    *,
    events: list[dict],
    child_stderr: str,
    timed_out: bool,
    oversized: bool,
    child_exit: int | None,
    assertions_spec: list[dict],
    refs: dict,
    runtime_source: Any,
    started: float,
) -> dict:
    cells: list = []
    executed_upto: str | None = None
    reached_end = False
    expr_items: dict = {}
    rows_events: dict = {}
    var_payloads: dict = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("t")
        if kind == "done":
            cells = event.get("cells") if isinstance(event.get("cells"), list) else []
            executed_upto = event.get("executedUpto")
            reached_end = bool(event.get("reachedEnd"))
        elif kind == "assertions":
            for item in event.get("items") or []:
                if isinstance(item, dict) and item.get("id") is not None:
                    expr_items[item["id"]] = item
        elif kind == "rows":
            if event.get("id") is not None:
                rows_events[event["id"]] = event
        elif kind == "vars":
            candidate = event.get("vars")
            if isinstance(candidate, dict):
                var_payloads.update(candidate)

    child_error = ""
    if timed_out:
        child_error = "学员代码执行超时"
    elif oversized:
        child_error = "学员代码结果超出回传上限"
    elif not events and child_stderr:
        child_error = (
            "学员进程异常退出：" + child_stderr[-MAX_CHILD_ERROR_CHARS:].strip()
        )

    assertions: list[dict] = []
    assertions_skipped = False
    if assertions_spec:
        if not reached_end or executed_upto is None or not runtime_source:
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
                for index, item in enumerate(assertions_spec)
            ]
        else:
            runtime = None
            if any(
                s.get("type") in ("frame_equal", "schema", "sql_rows")
                for s in assertions_spec
            ):
                runtime = _load_runtime(runtime_source)
            values = {name: _reconstruct_var(p) for name, p in var_payloads.items()}
            for spec in assertions_spec:
                assertion_type = spec.get("type")
                if assertion_type == "expr_true":
                    # 过渡期：expr 需要学员命名空间里的对象，只能由子进程求值，
                    # 结果承认为不可信（P0-6 由内容迁移 + 类型契约修复）。
                    item = expr_items.get(spec.get("id"))
                    assertions.append(
                        item
                        if isinstance(item, dict)
                        else _error_item(spec, "学员进程未回传表达式断言结果")
                    )
                elif assertion_type == "sql_rows":
                    assertions.append(
                        _judge_sql(spec, rows_events.get(spec.get("id")), runtime, refs)
                    )
                else:  # frame_equal / schema
                    assertions.append(
                        _judge_frame(
                            spec, values.get(spec.get("var")), runtime, refs
                        )
                    )

    failed_assertion = next(
        (a for a in assertions if a.get("status") != "passed"), None
    )
    cell_failed = any(
        isinstance(item, dict) and item.get("status") == "error" for item in cells
    )

    if cell_failed:
        verdict = "execution_failed"
    elif assertions_skipped:
        verdict = "execution_failed"
    elif assertions_spec and failed_assertion is not None:
        verdict = "assertion_failed"
    else:
        verdict = "passed"

    payload = {
        "cells": cells,
        "assertions": assertions,
        "assertionsSkipped": assertions_skipped,
        "executedUpto": executed_upto,
        "verdict": verdict,
        "durationMs": int((time.perf_counter() - started) * 1000),
    }
    if child_error:
        payload["error"] = child_error
    return payload


def _read_framed_stdin() -> str | None:
    """读 ``8 字节小端长度前缀 + payload`` 的帧，返回解码后的文本。

    为什么不能 read-to-EOF：Docker ``attach`` 的 stdin 通道送不达 EOF
    （``shutdown(SHUT_WR)`` 只关本端，daemon 不会关容器 stdin，服务器实测）；
    本地管道虽能送 EOF，但两侧统一走帧协议，行为一致、测试同一套。
    帧头缺失 / 长度非法 / 读不满 payload 都返回 ``None``（按坏输入处理）。
    """
    try:
        header = sys.stdin.buffer.read(8)
    except (OSError, ValueError):
        return None
    if len(header) != 8:
        return None
    length = int.from_bytes(header, "little")
    if length <= 0 or length > 8 * 1024 * 1024:
        return None
    try:
        payload = sys.stdin.buffer.read(length)
    except (OSError, ValueError):
        return None
    if len(payload) != length:
        return None
    return payload.decode("utf-8", errors="replace")


def main() -> int:
    started = time.perf_counter()
    root = Path.cwd()

    raw = _read_framed_stdin()
    if raw is None:
        print("driver input frame is invalid", file=sys.stderr)
        return 2
    try:
        driver_input = json.loads(raw)
    except json.JSONDecodeError:
        print("driver input is not valid json", file=sys.stderr)
        return 2
    if not isinstance(driver_input, dict):
        print("driver input is not an object", file=sys.stderr)
        return 2

    nonce = str(driver_input.get("nonce") or "")
    assertions_spec = [
        item
        for item in (driver_input.get("assertions") or [])
        if isinstance(item, dict)
    ]
    refs = {
        str(key): value
        for key, value in (driver_input.get("refs") or {}).items()
    }
    runtime_source = driver_input.get("runtime")
    deadline_ms = int(driver_input.get("deadlineMs") or 0)
    child_input = driver_input.get("child") or {}

    child_payload = json.dumps(
        {
            "specs": [
                s for s in (child_input.get("specs") or []) if isinstance(s, dict)
            ],
            "runtime": runtime_source,
            "assertionVars": [
                n
                for n in (child_input.get("assertionVars") or [])
                if isinstance(n, str)
            ],
            "maxVarBytes": int(
                child_input.get("maxVarBytes") or RESULT_MAX_BYTES_DEFAULT
            ),
        },
        ensure_ascii=False,
    ).encode("utf-8")

    if deadline_ms > 0:
        deadline_seconds = (
            deadline_ms / 1000.0
            - (time.perf_counter() - started)
            - DEADLINE_MARGIN_SECONDS
        )
    else:
        deadline_seconds = 60.0
    max_bytes = int(
        child_input.get("maxVarBytes") or RESULT_MAX_BYTES_DEFAULT
    ) + READ_CHUNK * 2

    raw_stdout, child_stderr, timed_out, child_exit, oversized = _run_child(
        root, child_payload, deadline_seconds, max_bytes
    )
    events = _parse_events(raw_stdout)

    if driver_input.get("observationMode"):
        done = next((e for e in events if e.get("t") == "done"), {})
        error = ("学员代码执行超时" if timed_out else
                 "学员代码结果超出回传上限" if oversized else
                 f"学员进程异常退出：{child_stderr[-500:]}" if child_exit else "")
        payload = {
            "cells": done.get("cells", []), "executedUpto": done.get("executedUpto"),
            "assertions": [], "assertionsSkipped": True,
            "verdict": "execution_failed", "error": error,
            "observations": [e for e in events if e.get("t") in ("vars", "rows", "call")],
        }
        # Docker json-file logging may split a UTF-8 sequence at its chunk limit.
        # ASCII JSON escapes keep long table observations lossless across chunks.
        print(MARKER + nonce + json.dumps(payload, ensure_ascii=True))
        return 0

    payload = _build_payload(
        events=events,
        child_stderr=child_stderr,
        timed_out=timed_out,
        oversized=oversized,
        child_exit=child_exit,
        assertions_spec=assertions_spec,
        refs=refs,
        runtime_source=runtime_source,
        started=started,
    )
    print(MARKER + nonce + json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - 沙箱入口
    sys.exit(main())
