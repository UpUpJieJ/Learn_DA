"""Session execution tests — driver + workspace plumbing on the local provider.

These exercise the *real* assertion runtime from the backend repo
(``learn_da/app/practice/assertion_runtime.py``), so a DSL change that breaks
session evaluation fails here too.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

from runner.local_provider import LocalSubprocessProvider
from runner.schemas import ExecutionStatus, RunnerSessionRequest, SessionCell

RUNTIME_PATH = (
    Path(__file__).resolve().parents[2]
    / "learn_da"
    / "app"
    / "practice"
    / "assertion_runtime.py"
)

CSV = "region,amount\n华东,10\n华北,20\n"

CELL_READ = (
    "import csv\n"
    "with open('data/demo/sales.csv', encoding='utf-8') as handle:\n"
    "    rows = list(csv.DictReader(handle))\n"
    "total = sum(int(row['amount']) for row in rows)\n"
    "print('rows', len(rows))\n"
)
CELL_PRINT = "print('total is', total)\n"
CELL_LAST = "print('done')\n"


def _provider() -> LocalSubprocessProvider:
    # sys.executable keeps the test hermetic: no polars/duckdb needed here.
    return LocalSubprocessProvider(python_executable=sys.executable, timeout_seconds=30)


def _request(**overrides) -> RunnerSessionRequest:
    runtime = RUNTIME_PATH.read_text(encoding="utf-8") if RUNTIME_PATH.exists() else ""
    payload = {
        "requestId": "11111111-1111-1111-1111-111111111111",
        "cells": [
            SessionCell(cellId="c1", code=CELL_READ),
            SessionCell(cellId="c2", code=CELL_PRINT),
            SessionCell(cellId="c3", code=CELL_LAST),
        ],
        "datasets": {"demo/sales.csv": base64.b64encode(CSV.encode()).decode()},
        "runtime": runtime,
        "assertions": [
            {
                "id": "a1",
                "type": "expr_true",
                "title": "合计为 30",
                "expr": "total == 30",
            }
        ],
    }
    payload.update(overrides)
    return RunnerSessionRequest(**payload)


def test_full_replay_passes_assertions():
    result = _provider().execute_session(_request())

    assert result["status"] == ExecutionStatus.SUCCESS
    assert result["verdict"] == "passed"
    assert [cell["cellId"] for cell in result["cells"]] == ["c1", "c2", "c3"]
    assert [cell["status"] for cell in result["cells"]] == ["success"] * 3
    # Cells share one namespace: c2 sees `total` defined by c1.
    assert "rows 2" in result["cells"][0]["stdout"]
    assert "total is 30" in result["cells"][1]["stdout"]
    assert result["assertions"][0]["status"] == "passed"
    assert result["executedUpto"] == "c3"


def test_assertion_failure_reports_actual_value():
    request = _request(
        assertions=[
            {
                "id": "a1",
                "type": "expr_true",
                "title": "合计为 99",
                "expr": "total == 99",
            }
        ]
    )

    result = _provider().execute_session(request)

    assert result["verdict"] == "assertion_failed"
    assertion = result["assertions"][0]
    assert assertion["status"] == "failed"
    # The failing expression is echoed so the learner sees what was checked...
    assert "total == 99" in assertion["actual"]
    # ...and the value polars/python actually produced.
    assert "False" in assertion["actual"]


def test_failed_cell_stops_replay_and_skips_assertions():
    cells = [
        SessionCell(cellId="c1", code=CELL_READ),
        SessionCell(cellId="c2", code="raise ValueError('boom')\n"),
        SessionCell(cellId="c3", code=CELL_LAST),
    ]

    result = _provider().execute_session(_request(cells=cells))

    assert result["verdict"] == "execution_failed"
    assert [cell["status"] for cell in result["cells"]] == ["success", "error", "skipped"]
    assert result["cells"][1]["errorType"] == "ValueError"
    assert "boom" in result["cells"][1]["stderr"]
    assert result["assertionsSkipped"] is True
    assert result["assertions"][0]["status"] == "skipped"
    assert result["executedUpto"] is None


def test_stop_at_limits_execution_to_prefix():
    result = _provider().execute_session(_request(stopAt="c2"))

    assert [cell["status"] for cell in result["cells"]] == ["success", "success", "skipped"]
    assert result["executedUpto"] == "c2"
    # The prefix is complete, so assertions still run.
    assert result["verdict"] == "passed"


def test_cells_do_not_leak_between_requests():
    provider = _provider()
    provider.execute_session(_request())

    # A fresh request that never defines `total` must fail at the assertion,
    # proving each execution gets a brand new namespace.
    cells = [SessionCell(cellId="c1", code="amount = 1\n")]
    result = provider.execute_session(
        _request(cells=cells, datasets={}, assertions=[{
            "id": "a1", "type": "expr_true", "title": "total", "expr": "total == 30",
        }])
    )

    assert result["assertions"][0]["status"] == "error"
    assert result["verdict"] == "assertion_failed"


@pytest.mark.parametrize("bad_path", ["../escape.csv", "/etc/passwd", "C:/windows/x.csv"])
def test_dataset_path_escape_is_rejected(bad_path):
    result = _provider().execute_session(
        _request(datasets={bad_path: base64.b64encode(b"x").decode()})
    )

    assert result["status"] == ExecutionStatus.REJECTED
    assert result["errorType"] == "invalid_session_request"
    assert "unsafe dataset path" in result["error"]


def test_oversized_dataset_is_rejected(monkeypatch):
    from runner.settings import runner_settings

    monkeypatch.setattr(runner_settings, "RUNNER_SESSION_MAX_DATASET_BYTES", 8)
    result = _provider().execute_session(
        _request(datasets={"demo/sales.csv": base64.b64encode(b"0123456789").decode()})
    )

    assert result["status"] == ExecutionStatus.REJECTED
    assert "exceed" in result["error"]


def test_missing_runtime_reports_protocol_error():
    result = _provider().execute_session(_request(runtime=None))

    assert result["status"] == ExecutionStatus.SUCCESS  # driver itself ran
    # Without the runtime module the assertions cannot be evaluated.
    assert result["verdict"] == "execution_failed"