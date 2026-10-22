"""课程地图进度与学习报告（改版 P1/P3）行为测试。

直接往 ``task_attempts`` 写记录，验证统计口径：首次通过、失败模式、连续天数、track 汇总。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.workspace.models import TaskAttempt

pytestmark = pytest.mark.anyio

LESSON = "polars-groupby"
VISITOR = "visitor-progress"


@pytest.fixture()
def visitor(client):
    """把匿名访客固定成 VISITOR，这样测试可以直接写 task_attempts 再读接口。"""
    from main import app
    from app.core.session import get_anonymous_visitor_id

    app.dependency_overrides[get_anonymous_visitor_id] = lambda: VISITOR
    return VISITOR


async def _attempt(
    db_session,
    *,
    task_id: str,
    status: str,
    assertions: str = "[]",
    attempt_no: int = 1,
    days_ago: int = 0,
    visitor: str = VISITOR,
) -> TaskAttempt:
    row = TaskAttempt(
        visitor_id=visitor,
        session_id=1,
        lesson_slug=LESSON,
        task_id=task_id,
        attempt_no=attempt_no,
        status=status,
        code="",
        actual="",
        assertions=assertions,
        is_confirmed=False,
        created_time=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def test_progress_is_empty_before_any_attempt(client, visitor):
    body = (await client.get("/api/v1/workspace/progress")).json()["data"]

    assert body["summary"]["attemptsTotal"] == 0
    assert body["summary"]["lessonsStarted"] == 0
    assert body["lessons"], "课程列表不应为空"
    assert all(row["status"] == "not_started" for row in body["lessons"])
    assert all(row["passedTasks"] == 0 for row in body["lessons"])
    polars = next(row for row in body["lessons"] if row["lessonSlug"] == LESSON)
    assert polars["totalTasks"] == 2
    assert polars["currentTaskId"] == "t1"


async def test_progress_counts_passed_tasks_and_current_task(client, visitor, db_session):
    await _attempt(db_session, task_id="t1", status="passed")

    body = (await client.get("/api/v1/workspace/progress")).json()["data"]
    polars = next(row for row in body["lessons"] if row["lessonSlug"] == LESSON)

    assert polars["passedTasks"] == 1
    assert polars["status"] == "in_progress"
    assert polars["currentTaskId"] == "t2"
    assert polars["attempts"] == 1
    assert body["summary"]["lessonsStarted"] == 1
    assert body["summary"]["lessonsCompleted"] == 0


async def test_progress_marks_lesson_completed_when_all_tasks_pass(client, visitor, db_session):
    await _attempt(db_session, task_id="t1", status="passed")
    await _attempt(db_session, task_id="t2", status="passed")

    body = (await client.get("/api/v1/workspace/progress")).json()["data"]
    polars = next(row for row in body["lessons"] if row["lessonSlug"] == LESSON)

    assert polars["status"] == "completed"
    assert polars["passedTasks"] == 2
    assert polars["currentTaskId"] is None
    assert body["summary"]["lessonsCompleted"] == 1

    tracks = {row["track"]: row for row in body["tracks"]}
    assert tracks["polars_basics"]["passedTasks"] >= 2


async def test_report_collects_error_patterns_and_first_try(client, visitor, db_session):
    failed = (
        '[{"id": "t1-schema", "type": "schema", "title": "结果包含三列",'
        ' "status": "failed", "actual": "缺少列 [\'revenue\']"},'
        ' {"id": "t1-rows", "type": "expr_true", "title": "四个区域",'
        ' "status": "passed", "actual": ""}]'
    )
    await _attempt(db_session, task_id="t1", status="failed", assertions=failed, attempt_no=1)
    await _attempt(db_session, task_id="t1", status="passed", attempt_no=2)
    await _attempt(db_session, task_id="t2", status="skipped", attempt_no=1, days_ago=3)

    body = (await client.get("/api/v1/workspace/report")).json()["data"]

    assert body["summary"]["attemptsTotal"] == 3
    # t1 第一次失败、t2 第一次是 skipped → 没有任何任务一次过
    assert body["summary"]["tasksFirstTry"] == 0
    assert body["summary"]["activeDays"] == 2
    assert body["summary"]["streakDays"] == 1, "3 天前那次已断签"

    patterns = body["errorPatterns"]
    assert patterns, "失败尝试应产出错误模式"
    assert patterns[0]["assertionId"] == "t1-schema"
    assert patterns[0]["count"] == 1
    assert "缺少列" in patterns[0]["lastActual"]
    assert patterns[0]["taskTitle"], "错误模式要带任务标题"

    recent = body["recent"]
    assert len(recent) == 3
    # 最近提交按时间倒序：t1（今天通过） > t1（今天失败） > t2（3 天前跳过）
    assert recent[0]["taskId"] == "t1"
    assert recent[0]["status"] == "passed"
    assert recent[-1]["taskId"] == "t2"
    assert recent[-1]["createdAt"]


async def test_report_is_honest_without_data(client, visitor):
    body = (await client.get("/api/v1/workspace/report")).json()["data"]

    assert body["errorPatterns"] == []
    assert body["recent"] == []
    assert body["summary"]["attemptsTotal"] == 0
    assert body["summary"]["streakDays"] == 0
    assert body["summary"]["lastActiveAt"] is None
    assert all(row["ratio"] == 0.0 for row in body["tracks"])