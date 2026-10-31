"""Session execution harness — shared plumbing for both providers.

A *session* is a replay-style run of a whole cell list (see the redesign doc
§3.2). The provider prepares a throw-away working directory::

    <work>/
      driver.py             # runner/session_driver.py — 判定 parent 进程
      learner_child.py      # runner/learner_child.py — 学员代码子进程
      plan.json             # {cells, stopAt} —— 学员可读，不含任何机密
      data/<dataset path>   # decoded from the request (base64)

then runs ``python -X utf8 -B driver.py`` with ``<work>`` as the working
directory. The provider feeds the driver one JSON document on **stdin**:
assertion specs, refs, the assertion-runtime source, a per-session nonce and
the deadline (see :func:`build_driver_input` — this never lands on disk, so
the learner's process never sees the refs). The driver prints one
``MARKER + nonce + JSON`` line holding the result.

Keeping the driver on disk (rather than ``python -c``) is deliberate: the
execution endpoint caps code at 5000 characters, and a session program is far
longer than that.
"""

from __future__ import annotations

import base64
import json
import shutil
import struct
from pathlib import Path, PureWindowsPath
from typing import Any

from runner.schemas import RunnerSessionRequest
from runner.settings import runner_settings

DRIVER_FILENAME = "driver.py"
CHILD_FILENAME = "learner_child.py"
PLAN_FILENAME = "plan.json"
DATA_DIRNAME = "data"

_DRIVER_PATH = Path(__file__).with_name("session_driver.py")
_CHILD_PATH = Path(__file__).with_name("learner_child.py")


class SessionWorkspaceError(ValueError):
    """Raised when the request cannot be materialised safely."""


def _safe_relative(path: str) -> Path:
    """Reject absolute paths and ``..`` escapes in dataset names."""
    candidate = Path(path.replace("\\", "/"))
    # PureWindowsPath("/etc/passwd").is_absolute() is False, and POSIX-absolute
    # paths still must not be honoured on Windows, so check the leading slash.
    if path.startswith(("/", "\\")) or candidate.is_absolute() or PureWindowsPath(path).drive:
        raise SessionWorkspaceError(f"unsafe dataset path: {path!r}")
    if any(part == ".." for part in candidate.parts):
        raise SessionWorkspaceError(f"unsafe dataset path: {path!r}")
    if not candidate.parts or candidate.parts[0] == "":
        raise SessionWorkspaceError(f"empty dataset path: {path!r}")
    return candidate


def prepare_workspace(work: Path, request: RunnerSessionRequest) -> None:
    """Write driver, learner child, plan and datasets into ``work``.

    判定材料（assertions / refs / runtime 源码）**不落盘**：它们经 driver 的
    stdin 传入（见 :func:`build_driver_input`）。``plan.json`` 只描述格清单，
    学员代码可以读它，但里面没有任何秘密。
    """
    work.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_DRIVER_PATH, work / DRIVER_FILENAME)
    shutil.copyfile(_CHILD_PATH, work / CHILD_FILENAME)

    total_bytes = 0
    for name, payload in (request.datasets or {}).items():
        target = work / DATA_DIRNAME / _safe_relative(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw = base64.b64decode(payload, validate=False)
        except Exception as exc:  # noqa: BLE001 - bad payload is a client error
            raise SessionWorkspaceError(f"dataset {name!r} is not valid base64") from exc
        total_bytes += len(raw)
        if total_bytes > runner_settings.RUNNER_SESSION_MAX_DATASET_BYTES:
            raise SessionWorkspaceError(
                "datasets exceed "
                f"{runner_settings.RUNNER_SESSION_MAX_DATASET_BYTES} bytes"
            )
        target.write_bytes(raw)

    plan = {
        "cells": [
            {"cellId": cell.cell_id, "code": cell.code, "language": cell.language}
            for cell in request.cells
        ],
        "stopAt": request.stop_at,
    }
    (work / PLAN_FILENAME).write_text(
        json.dumps(plan, ensure_ascii=False), encoding="utf-8"
    )


def build_driver_input(request: RunnerSessionRequest, nonce: str) -> str:
    """组装写进 driver stdin 的 JSON 文档（判定材料，永不落盘）。

    * ``refs`` / ``runtime`` / 完整 ``assertions`` 只进 driver（parent）；
    * 子进程只拿到 expr_true / sql_rows 的 specs（需要学员命名空间里的对象）
      与 frame_equal / schema 要回传的变量名清单，**拿不到 refs**；
    * ``deadlineMs`` 让 parent 自管子进程超时，比 provider 的会话期限先到。
    """
    assertions = [
        item for item in (request.assertions or []) if isinstance(item, dict)
    ]
    child_specs = [
        item
        for item in assertions
        if item.get("type") in ("expr_true", "sql_rows", "call")
    ]
    var_names = sorted(
        {
            item["var"]
            for item in assertions
            if item.get("type") in ("frame_equal", "schema", "value") and item.get("var")
        }
    )
    driver_input = {
        "observationMode": request.observation_mode,
        "nonce": nonce,
        "deadlineMs": runner_settings.RUNNER_SESSION_TIMEOUT_SECONDS * 1000,
        "assertions": assertions,
        "refs": dict(request.refs or {}),
        "runtime": request.runtime or None,
        "child": {
            "specs": child_specs,
            "assertionVars": var_names,
            "maxVarBytes": runner_settings.RUNNER_SESSION_MAX_RESULT_BYTES,
        },
    }
    return json.dumps(driver_input, ensure_ascii=False)


# 8 字节小端长度上限：driver 侧会拒绝超过该值的帧，两侧常量必须一致。
DRIVER_INPUT_MAX_BYTES = 8 * 1024 * 1024


def frame_driver_input(request: RunnerSessionRequest, nonce: str) -> bytes:
    """把 :func:`build_driver_input` 的 JSON 包成 ``长度前缀 + payload`` 的帧。

    Docker 的 ``attach`` stdin 通道**送不达 EOF**（``shutdown(SHUT_WR)`` 只关
    本端写侧，daemon 不会跟着关容器 stdin——服务器实测容器里的 ``tr`` 在
    shutdown 后仍 running），所以 driver 不能用 read-to-EOF 读输入，必须按
    帧头声明的长度精确读取。本地管道走同一协议，两侧行为一致。
    """
    payload = build_driver_input(request, nonce).encode("utf-8")
    if len(payload) > DRIVER_INPUT_MAX_BYTES:
        raise ValueError(
            "driver input exceeds %d bytes" % DRIVER_INPUT_MAX_BYTES
        )
    return struct.pack("<Q", len(payload)) + payload


def parse_driver_output(
    stdout_text: str, marker: str, nonce: str = ""
) -> dict[str, Any] | None:
    """Return the JSON payload printed by the driver, or ``None``.

    带上 ``nonce`` 时只认 ``marker + nonce + JSON`` 的行：学员侧伪造的
    marker 行没有 nonce，直接跳过（最多造成协议错误，伪造不出结论）。
    """
    for line in reversed(stdout_text.splitlines()):
        if not line.startswith(marker):
            continue
        rest = line[len(marker) :]
        if nonce:
            if not rest.startswith(nonce):
                continue
            rest = rest[len(nonce) :]
        try:
            return json.loads(rest)
        except json.JSONDecodeError:
            return None
    return None


def failure_payload(message: str) -> dict[str, Any]:
    """A payload shaped like a driver result but representing a hard failure."""
    return {
        "cells": [],
        "assertions": [],
        "assertionsSkipped": True,
        "executedUpto": None,
        "verdict": "execution_failed",
        "durationMs": 0,
        "error": message,
    }


def build_result(
    *,
    request_id: str,
    execution_id: str,
    status: str,
    payload: dict[str, Any] | None,
    duration_ms: int,
    error_type: str | None,
    error_message: str = "",
) -> dict[str, Any]:
    """Assemble the wire result for a session execution."""
    payload = payload or failure_payload(error_message or "no driver output")
    return {
        "requestId": request_id,
        "executionId": execution_id,
        "status": status,
        "verdict": payload.get("verdict", "execution_failed"),
        "cells": payload.get("cells", []),
        "assertions": payload.get("assertions", []),
        "assertionsSkipped": bool(payload.get("assertionsSkipped", True)),
        "executedUpto": payload.get("executedUpto"),
        "durationMs": duration_ms,
        "errorType": error_type,
        "error": payload.get("error", ""),
        "observations": payload.get("observations", []),
    }
