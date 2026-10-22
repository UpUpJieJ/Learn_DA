"""工作区 API（改版 M1）行为测试。

Runner 用 AsyncMock 替身，只验证服务端语义：
级联失效、任务状态、幂等、断言失败回传、跳过断言。
"""

from __future__ import annotations

import base64
import uuid
from typing import Any

import pytest

pytestmark = pytest.mark.anyio

LESSON = "polars-groupby"
DATASET = "ecommerce/orders.csv"


def _payload(
    *,
    cells: list[str],
    stop_at: str,
    verdict: str = "passed",
    assertions: list[dict[str, Any]] | None = None,
    skipped: bool = False,
) -> dict[str, Any]:
    return {
        "requestId": str(uuid.uuid4()),
        "executionId": str(uuid.uuid4()),
        "status": "success",
        "verdict": verdict,
        "cells": [
            {
                "cellId": cell_id,
                "status": "success",
                "stdout": "",
                "stderr": "",
                "durationMs": 5,
            }
            for cell_id in cells
        ],
        "assertions": assertions or [],
        "assertionsSkipped": skipped,
        "executedUpto": stop_at,
        "durationMs": 12,
        "errorType": None,
        "error": None,
    }


def _assertion(status: str, actual: str = "") -> dict[str, Any]:
    return {
        "id": "t1-schema",
        "type": "schema",
        "title": "结果包含三列",
        "status": status,
        "actual": actual,
        "detail": "",
        "durationMs": 1,
    }


async def _create(client) -> dict[str, Any]:
    response = await client.post("/api/v1/workspace/sessions", json={"lessonSlug": LESSON})
    assert response.status_code == 200
    return response.json()["data"]


async def _runner(client):
    from main import app

    return app.state.runner_client


async def test_create_session_lists_cells_tasks_and_datasets(client):
    data = await _create(client)

    assert [cell["cellId"] for cell in data["cells"]] == ["c1", "c2", "c3"]
    assert [cell["kind"] for cell in data["cells"]] == ["starter", "task", "task"]
    assert [cell["status"] for cell in data["cells"]] == ["stale", "stale", "stale"]
    assert data["datasets"] == [DATASET]
    assert [task["taskId"] for task in data["tasks"]] == ["t1", "t2"]
    assert all(task["status"] == "todo" for task in data["tasks"])
    assert [cell["hasAssertions"] for cell in data["cells"]] == [False, True, True]
    assert data["staleFrom"] == "c1"


async def test_repeated_create_reuses_same_session(client):
    first = await _create(client)
    second = await _create(client)

    assert first["sessionId"] == second["sessionId"]


async def test_run_cell_sends_prefix_and_updates_status(client):
    data = await _create(client)
    runner = await _runner(client)
    runner.execute_session.return_value = _payload(cells=["c1"], stop_at="c1")

    response = await client.post(
        f"/api/v1/workspace/sessions/{data['sessionId']}/cells/c1/run",
        json={"requestId": "run-c1"},
    )
    body = response.json()["data"]

    assert body["verdict"] == "passed"
    assert body["assertionsSkipped"] is False

    sent = runner.execute_session.await_args.args[0]
    assert [cell["cellId"] for cell in sent["cells"]] == ["c1"]
    assert sent["stopAt"] == "c1"
    assert sent["assertions"] == []
    assert DATASET in sent["datasets"]
    assert base64.b64decode(sent["datasets"][DATASET]).startswith(b"order_id")
    assert "def run(" in sent["runtime"]

    snapshot = await client.get(f"/api/v1/workspace/sessions/{data['sessionId']}")
    snapshot_body = snapshot.json()["data"]
    statuses = {cell["cellId"]: cell["status"] for cell in snapshot_body["cells"]}
    assert statuses == {"c1": "ok", "c2": "stale", "c3": "stale"}


async def test_submit_task_passes_and_records_attempt(client):
    data = await _create(client)
    runner = await _runner(client)
    runner.execute_session.return_value = _payload(
        cells=["c1", "c2"], stop_at="c2", assertions=[_assertion("passed")]
    )

    response = await client.post(
        f"/api/v1/workspace/sessions/{data['sessionId']}/tasks/t1/submit",
        json={"requestId": "submit-t1"},
    )
    body = response.json()["data"]

    assert body["verdict"] == "passed"
    assert body["taskStatus"] == "passed"

    sent = runner.execute_session.await_args.args[0]
    assert [cell["cellId"] for cell in sent["cells"]] == ["c1", "c2"]
    assert len(sent["assertions"]) == 3

    snapshot = (await client.get(f"/api/v1/workspace/sessions/{data['sessionId']}")).json()[
        "data"
    ]
    tasks = {task["taskId"]: task["status"] for task in snapshot["tasks"]}
    assert tasks == {"t1": "passed", "t2": "todo"}


async def test_assertion_failure_carries_actual_and_marks_failed(client):
    data = await _create(client)
    runner = await _runner(client)
    runner.execute_session.return_value = _payload(
        cells=["c1", "c2"],
        stop_at="c2",
        verdict="assertion_failed",
        assertions=[_assertion("failed", "缺少列 ['revenue']（实际列：['region']）")],
    )

    response = await client.post(
        f"/api/v1/workspace/sessions/{data['sessionId']}/tasks/t1/submit",
        json={"requestId": "submit-t1-fail"},
    )
    body = response.json()["data"]

    assert body["verdict"] == "assertion_failed"
    assert body["taskStatus"] == "failed"
    assert "revenue" in body["assertions"][0]["actual"]

    snapshot = (await client.get(f"/api/v1/workspace/sessions/{data['sessionId']}")).json()[
        "data"
    ]
    assert {task["taskId"]: task["status"] for task in snapshot["tasks"]}["t1"] == "failed"


async def test_skipped_assertions_mark_task_skipped(client):
    data = await _create(client)
    runner = await _runner(client)
    runner.execute_session.return_value = _payload(
        cells=["c1", "c2"],
        stop_at="c2",
        verdict="execution_failed",
        assertions=[_assertion("skipped")],
        skipped=True,
    )

    body = (
        await client.post(
            f"/api/v1/workspace/sessions/{data['sessionId']}/tasks/t1/submit",
            json={"requestId": "submit-skipped"},
        )
    ).json()["data"]

    assert body["assertionsSkipped"] is True
    assert body["taskStatus"] == "skipped"


async def test_editing_earlier_cell_invalidates_later_cells_and_passed_task(client):
    data = await _create(client)
    runner = await _runner(client)
    runner.execute_session.return_value = _payload(
        cells=["c1", "c2"], stop_at="c2", assertions=[_assertion("passed")]
    )
    await client.post(
        f"/api/v1/workspace/sessions/{data['sessionId']}/tasks/t1/submit",
        json={"requestId": "submit-t1-ok"},
    )

    edited = await client.put(
        f"/api/v1/workspace/sessions/{data['sessionId']}/cells/c1",
        json={"code": "orders = None\n"},
    )
    body = edited.json()["data"]

    statuses = {cell["cellId"]: cell["status"] for cell in body["cells"]}
    assert statuses == {"c1": "stale", "c2": "stale", "c3": "stale"}
    # 结论依赖 c2 的执行结果，但 c2 已被上游改动失效 → 需要复核
    assert {task["taskId"]: task["status"] for task in body["tasks"]}["t1"] == "todo"


async def test_same_request_id_is_idempotent(client):
    data = await _create(client)
    runner = await _runner(client)
    runner.execute_session.return_value = _payload(cells=["c1"], stop_at="c1")

    url = f"/api/v1/workspace/sessions/{data['sessionId']}/cells/c1/run"
    first = (await client.post(url, json={"requestId": "dup-1"})).json()["data"]
    second = (await client.post(url, json={"requestId": "dup-1"})).json()["data"]

    assert first["verdict"] == second["verdict"] == "passed"
    assert runner.execute_session.await_count == 1


async def test_unknown_lesson_and_cell_are_404(client):
    missing_lesson = await client.post(
        "/api/v1/workspace/sessions", json={"lessonSlug": "no-such-lesson"}
    )
    assert missing_lesson.json()["code"] == 404

    data = await _create(client)
    unknown_cell = await client.post(
        f"/api/v1/workspace/sessions/{data['sessionId']}/cells/nope/run",
        json={"requestId": "nope"},
    )
    assert unknown_cell.json()["code"] == 404


async def test_session_is_scoped_to_visitor(client):
    data = await _create(client)
    other = await client.get(
        f"/api/v1/workspace/sessions/{data['sessionId']}",
        headers={"Cookie": "learn_da_visitor=someone-else"},
    )
    assert other.json()["code"] == 404