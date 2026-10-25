"""分级提示（ladder，改版 E2）：层级公式、确定性文案、API 行为。

锁住四件事：

* 层级按**真实失败次数 + 已用层数**算，与「问了几次」无关；
* 客户端没有「要第几层」的参数，越层请求天然无效；
* 每要一次都落 ``hint_usages``，所以「已用层数」是服务端权威；
* 第 1/2/3 层逐级披露更多，但**始终不给整格可提交代码**。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.workspace.hints import (
    HINT_MAX_LEVEL,
    HintState,
    build_hint_content,
    compute_level,
    normalize_error,
)

pytestmark = pytest.mark.anyio

LESSON = "polars-groupby"


# ----------------------------------------------------------------------
# 层级公式
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("failures", "hints_used", "expected"),
    [
        (0, 0, 1),
        (1, 0, 1),  # 失败一次先给最轻的 L1，不直接跳到「复述实际值」
        (2, 0, 2),
        (3, 0, 2),
        (4, 0, 3),  # 连续失败 4 次才到 L3（真卡住的人拿得到）
        (5, 0, 3),
        (0, 1, 2),
        (0, 2, 3),
        (0, 9, 3),
        (-3, -2, 1),  # 脏数据不得把层级压到 1 以下
    ],
)
def test_compute_level(failures: int, hints_used: int, expected: int):
    assert compute_level(failures, hints_used) == expected


def test_a_single_failure_does_not_skip_the_lightest_level():
    """失败一次就该拿到 L1。

    旧公式 ``1 + failures + hints_used`` 会让第一次失败后点提示直接是 L2
    （把学习者刚看到过的实际值再说一遍），L1 实际上永远拿不到——这是实跑
    时发现的，不是推测。
    """
    assert compute_level(1, 0) == 1
    assert compute_level(4, 0) == 3


def test_repeated_failures_still_reach_the_deepest_level():
    """「连续失败很多次但不提问」也必须能拿到 L3（旧实现的另一个方向错误）。"""
    assert compute_level(9, 0) == HINT_MAX_LEVEL


def test_compute_level_is_capped_at_three():
    assert compute_level(99, 99) == HINT_MAX_LEVEL


# ----------------------------------------------------------------------
# 确定性文案
# ----------------------------------------------------------------------


def _assertion(status: str, *, detail: str = "", actual: str = "", title: str = "") -> dict[str, Any]:
    return {
        "id": "t1-schema",
        "type": "schema",
        "title": title or "结果包含三列",
        "status": status,
        "actual": actual,
        "detail": detail,
    }


def test_level_one_only_points_at_the_symptom():
    content = build_hint_content(
        1,
        task_title="按区域聚合",
        task_objective="按 region 聚合出 revenue 与 orders",
        assertions=[
            _assertion(
                "failed",
                detail="缺少列 ['revenue']（实际列：['region', 'quantity']）",
            )
        ],
    )

    assert "提示 L1／3" in content
    assert "还没通过的断言" in content
    assert "结果包含三列" in content
    # L1 不点名具体 API，也不给「要改的地方」
    assert "可以查的 API" not in content
    assert "要改的地方" not in content


def test_level_two_adds_actual_values_and_api_names():
    content = build_hint_content(
        2,
        task_title="按区域聚合",
        task_objective="按 region 聚合",
        assertions=[
            _assertion(
                "failed",
                detail="缺少列 ['revenue']（实际列：['region', 'quantity']）",
            )
        ],
    )

    assert "服务端判定给出的实际值" in content
    assert "revenue" in content
    assert "常见原因" in content
    assert "可以查的 API" in content
    assert "alias" in content
    # 仍是「查什么」，不给出可复制的整行代码
    assert "要改的地方" not in content


def test_level_three_names_the_missing_column_but_not_the_answer():
    content = build_hint_content(
        3,
        task_title="按区域聚合",
        task_objective="按 region 聚合",
        assertions=[
            _assertion(
                "failed",
                detail="缺少列 ['revenue']（实际列：['region', 'quantity']）",
            )
        ],
    )

    assert "要改的地方" in content
    assert "`revenue`" in content
    assert "不要整格重写" in content
    # 关键约束：任何一层都不给整格可提交代码（只允许 `pl.col(...)` 这类
    # 带省略号的 API 名称，不允许出现可整行复制的赋值语句）
    assert "group_by(" not in content
    assert "group_by('region')" not in content
    for line in content.splitlines():
        if line.startswith("- ") or line.startswith("**"):
            continue
        assert "=" not in line, f"提示里出现了可复制代码：{line}"


def test_hint_without_failures_does_not_invent_an_error():
    content = build_hint_content(
        1,
        task_title="按区域聚合",
        task_objective="按 region 聚合出 revenue",
        assertions=[],
    )

    assert "还没有可用的失败记录" in content
    assert "先完整跑一遍" in content
    assert "任务要求：按 region 聚合出 revenue" in content


# ----------------------------------------------------------------------
# 代码没跑通时的提示（实跑发现：断言全 skipped，detail 只有「未求值」）
# ----------------------------------------------------------------------


def _skipped_assertions() -> list[dict[str, Any]]:
    return [
        {
            "id": f"t1-{name}",
            "type": "expr_true",
            "title": title,
            "status": "skipped",
            "actual": None,
            "detail": "前面的单元格未全部执行成功，断言未求值",
        }
        for name, title in (
            ("schema", "结果包含三列"),
            ("rows", "四个区域各一行"),
        )
    ]


def test_execution_failure_quotes_the_real_error_instead_of_skipped_assertions():
    """代码没跑通时必须报真实异常，而不是「断言未求值」这种无用信息。"""
    content = build_hint_content(
        1,
        task_title="按区域聚合销售额",
        task_objective="按 region 聚合",
        assertions=_skipped_assertions(),
        execution_failure='ColumnNotFoundError: unable to find column "revenue"; valid columns: ["region", "quantity"]',
    )

    assert "**报错**" in content
    assert "revenue" in content
    assert "unable to find column" in content
    # 断言未执行的噪音不该出现在文案里
    assert "断言未求值" not in content
    assert "还没通过的断言" not in content
    assert "在运行时直接报错了" in content


def test_duplicated_exception_prefix_is_collapsed():
    """真实 stderr 里类名会重复两次，必须归一，不能原样贴给学习者。"""
    raw = (
        "ColumnNotFoundError: polars.exceptions.ColumnNotFoundError: "
        'unable to find column "revenue"; valid columns: ["region", "quantity"]'
    )

    assert normalize_error(raw) == (
        'ColumnNotFoundError: unable to find column "revenue"; '
        'valid columns: ["region", "quantity"]'
    )
    # 已经干净的不动，带模块路径的剥成短类名
    assert normalize_error("ZeroDivisionError: division by zero") == (
        "ZeroDivisionError: division by zero"
    )
    assert normalize_error("polars.exceptions.ComputeError: boom") == "ComputeError: boom"
    # 没有类名的原样返回，不硬凑冒号
    assert normalize_error("plain message") == "plain message"
    assert normalize_error("") == ""


def test_execution_failure_hint_uses_the_valid_columns_from_the_error():
    """报错里的 valid columns 是这一格唯一可用的线索，必须用上。"""
    content = build_hint_content(
        1,
        task_title="按区域聚合销售额",
        task_objective="按 region 聚合",
        assertions=_skipped_assertions(),
        execution_failure=(
            "ColumnNotFoundError: polars.exceptions.ColumnNotFoundError: "
            'unable to find column "revenue"; valid columns: ["region", "quantity"]'
        ),
    )

    # 报错归一（不重复类名）+ 点名取不到的列 + 列出真实可用的列
    assert content.count("ColumnNotFoundError") == 1
    assert "`revenue`" in content
    assert "`region`" in content and "`quantity`" in content


def test_execution_failure_hint_still_escalates_by_level():
    kwargs = dict(
        task_title="按区域聚合销售额",
        task_objective="按 region 聚合",
        assertions=_skipped_assertions(),
        execution_failure="ColumnNotFoundError: \"revenue\" not found",
    )

    level_one = build_hint_content(1, **kwargs)
    level_three = build_hint_content(3, **kwargs)

    # L1 只说「去定位这个名字」，不点名 API
    assert "可以查的 API" not in level_one
    # L3 给出「要改的地方」但仍不给整格代码
    assert "要改的地方" in level_three
    assert "group_by(" not in level_three
    for line in level_three.splitlines():
        if line.startswith("- ") or line.startswith("**"):
            continue
        assert "=" not in line, f"提示里出现了可复制代码：{line}"


def test_capped_hint_admits_there_is_nothing_deeper():
    """封顶后再点，不能假装又给了新一层。"""
    capped = build_hint_content(
        3,
        task_title="按区域聚合",
        task_objective="按 region 聚合",
        assertions=[_assertion("failed", detail="缺少列 ['revenue']")],
        hints_used=3,
    )
    not_capped = build_hint_content(
        3,
        task_title="按区域聚合",
        task_objective="按 region 聚合",
        assertions=[_assertion("failed", detail="缺少列 ['revenue']")],
        hints_used=1,
    )

    assert "这已经是最后一层提示" in capped
    assert "这已经是最后一层提示" not in not_capped


def test_hint_state_defaults_are_the_first_level():
    state = HintState(task_id="t1")

    assert state.level == 1
    assert state.hints_used == 0
    assert state.next_level == 1


# ----------------------------------------------------------------------
# API 行为（Runner 用 AsyncMock 替身）
# ----------------------------------------------------------------------


def _payload(verdict: str, assertions: list[dict[str, Any]]) -> dict[str, Any]:
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
            for cell_id in ("c1", "c2")
        ],
        "assertions": assertions,
        "assertionsSkipped": False,
        "executedUpto": "c2",
        "durationMs": 12,
        "errorType": None,
        "error": None,
    }


async def _create(client) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/workspace/sessions", json={"lessonSlug": LESSON}
    )
    assert response.status_code == 200
    return response.json()["data"]


async def _runner(client):
    from main import app

    return app.state.runner_client


async def _submit(client, session_id: int, request_id: str, verdict: str, actual: str):
    runner = await _runner(client)
    runner.execute_session.return_value = _payload(
        verdict,
        [
            {
                "id": "t1-schema",
                "type": "schema",
                "title": "结果包含三列",
                "status": "failed" if verdict != "passed" else "passed",
                "actual": actual,
                "detail": "",
                "durationMs": 1,
            }
        ],
    )
    return (
        await client.post(
            f"/api/v1/workspace/sessions/{session_id}/tasks/t1/submit",
            json={"requestId": request_id},
        )
    ).json()["data"]


async def _hint(client, session_id: int, task_id: str = "t1"):
    return await client.post(
        f"/api/v1/workspace/sessions/{session_id}/tasks/{task_id}/hint"
    )


async def test_first_hint_without_failures_is_level_one(client):
    data = await _create(client)

    body = (await _hint(client, data["sessionId"])).json()["data"]

    assert body["level"] == 1
    assert body["hintsUsed"] == 1
    assert body["maxLevel"] == 3
    assert body["hasNext"] is True
    # 没有失败记录时不编造具体错误
    assert "还没有可用的失败记录" in body["content"]


async def test_failures_raise_the_level_and_hints_are_recorded(client):
    data = await _create(client)
    session_id = data["sessionId"]

    first = (await _hint(client, session_id)).json()["data"]
    assert first["level"] == 1

    # 提示之后失败 1 次 -> 下一层是 L2（1 + 1 + 1）
    await _submit(client, session_id, "sub-fail-1", "assertion_failed", "缺少列 ['revenue']")
    second = (await _hint(client, session_id)).json()["data"]
    assert second["level"] == 2
    assert second["hintsUsed"] == 2
    assert "服务端判定给出的实际值" in second["content"]
    assert "revenue" in second["content"]

    # 再失败 1 次 -> L3（1 + 1 + 2）
    await _submit(client, session_id, "sub-fail-2", "assertion_failed", "缺少列 ['revenue']")
    third = (await _hint(client, session_id)).json()["data"]
    assert third["level"] == 3
    assert third["hintsUsed"] == 3
    assert third["hasNext"] is False
    assert "要改的地方" in third["content"]


async def test_snapshot_exposes_hint_progress_per_task(client):
    data = await _create(client)
    session_id = data["sessionId"]
    tasks = {task["taskId"]: task for task in data["tasks"]}
    assert tasks["t1"]["hintLevel"] == 1
    assert tasks["t1"]["hintsUsed"] == 0
    assert tasks["t1"]["hintMaxLevel"] == 3

    await _hint(client, session_id)
    snapshot = (
        await client.get(f"/api/v1/workspace/sessions/{session_id}")
    ).json()["data"]
    after = {task["taskId"]: task for task in snapshot["tasks"]}
    assert after["t1"]["hintsUsed"] == 1
    # 只影响被要提示的那个任务
    assert after["t2"]["hintsUsed"] == 0


async def test_unknown_task_hint_is_404(client):
    data = await _create(client)

    response = await _hint(client, data["sessionId"], "nope")

    assert response.json()["code"] == 404


async def test_hint_is_scoped_to_visitor(client):
    data = await _create(client)

    other = await client.post(
        f"/api/v1/workspace/sessions/{data['sessionId']}/tasks/t1/hint",
        headers={"Cookie": "learn_da_visitor=someone-else"},
    )

    assert other.json()["code"] == 404
