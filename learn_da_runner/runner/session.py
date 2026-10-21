"""Session execution harness — shared plumbing for both providers.

A *session* is a replay-style run of a whole cell list (see the redesign doc
§3.2). The provider prepares a throw-away working directory::

    <work>/
      driver.py             # runner/session_driver.py, copied verbatim
      plan.json             # cells / stopAt / assertions / refs
      assertion_runtime.py  # supplied by the backend, never bundled
      data/<dataset path>   # decoded from the request (base64)

then runs ``python -X utf8 -B driver.py`` with ``<work>`` as the working
directory. The driver prints one marker line holding the JSON result.

Keeping the driver on disk (rather than ``python -c``) is deliberate: the
execution endpoint caps code at 5000 characters, and a session program is far
longer than that.
"""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from typing import Any

from runner.schemas import RunnerSessionRequest
from runner.settings import runner_settings

DRIVER_FILENAME = "driver.py"
PLAN_FILENAME = "plan.json"
RUNTIME_FILENAME = "assertion_runtime.py"
DATA_DIRNAME = "data"

_DRIVER_PATH = Path(__file__).with_name("session_driver.py")


class SessionWorkspaceError(ValueError):
    """Raised when the request cannot be materialised safely."""


def _safe_relative(path: str) -> Path:
    """Reject absolute paths and ``..`` escapes in dataset names."""
    candidate = Path(path.replace("\\", "/"))
    # PureWindowsPath("/etc/passwd").is_absolute() is False, and POSIX-absolute
    # paths still must not be honoured on Windows, so check the leading slash.
    if path.startswith(("/", "\\")) or candidate.is_absolute():
        raise SessionWorkspaceError(f"unsafe dataset path: {path!r}")
    if any(part == ".." for part in candidate.parts):
        raise SessionWorkspaceError(f"unsafe dataset path: {path!r}")
    if not candidate.parts or candidate.parts[0] == "":
        raise SessionWorkspaceError(f"empty dataset path: {path!r}")
    return candidate


def prepare_workspace(work: Path, request: RunnerSessionRequest) -> None:
    """Write driver, plan, assertion runtime and datasets into ``work``."""
    work.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_DRIVER_PATH, work / DRIVER_FILENAME)

    runtime_file: str | None = None
    total_bytes = 0
    if request.runtime:
        runtime_file = RUNTIME_FILENAME
        (work / RUNTIME_FILENAME).write_text(request.runtime, encoding="utf-8")

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
        "assertions": request.assertions or [],
        "refs": request.refs or {},
        "runtimeFile": runtime_file,
    }
    (work / PLAN_FILENAME).write_text(
        json.dumps(plan, ensure_ascii=False), encoding="utf-8"
    )


def parse_driver_output(stdout_text: str, marker: str) -> dict[str, Any] | None:
    """Return the JSON payload printed by the driver, or ``None``."""
    for line in reversed(stdout_text.splitlines()):
        if line.startswith(marker):
            try:
                return json.loads(line[len(marker):])
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
    }