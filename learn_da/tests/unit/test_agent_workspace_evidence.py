"""Agent 证据链（改版 M4）：证据来自 ``task_attempts`` 而不是冻结的练习表。

这些测试只依赖数据库与内容索引，不需要 Runner：提交记录直接写库，
再由 ``AgentEvidenceResolver`` 解析，验证

* 五态推导用的是 Runner verdict（不是客户端自报）；
* 失败断言的 ``actual`` 会进入证据，模型才能说清"错在哪"；
* 任务进度 / 当前任务 / 课程完成度来自真实通过记录；
* ``attemptId`` 与 ``taskId`` 的越权或跨课引用不被采信。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.agent.evidence import (
    AgentEvidenceResolver,
    build_teaching_feedback,
    derive_next_action,
    derive_workspace_state,
)
from app.agent.prompts import build_evidence_block
from app.workspace.models import TaskAttempt
from app.workspace.repository import WorkspaceReadRepository

pytestmark = pytest.mark.anyio

LESSON = "polars-groupby"
OTHER_LESSON = "polars-basics"
VISITOR = "visitor-evidence"
OTHER_VISITOR = "visitor-intruder"

FAILED_ASSERTIONS = json.dumps(
    [
        {"id": "t1-schema", "title": "列齐全", "status": "passed", "detail": "", "actual": ""},
        {
            "id": "t1-rows",
            "title": "分组行数",
            "status": "failed",
            "detail": "表达式为假",
            "actual": "表达式 'region_stats.height == 4' 为假（实际值：False）",
        },
    ],
    ensure_ascii=False,
)


async def _attempt(
    db_session,
    *,
    task_id: str = "t1",
    status: str = "failed",
    verdict: str | None = "assertion_failed",
    assertions: str = FAILED_ASSERTIONS,
    attempt_no: int = 1,
    lesson_slug: str = LESSON,
    visitor: str = VISITOR,
    code: str = "import polars as pl",
) -> TaskAttempt:
    row = TaskAttempt(
        visitor_id=visitor,
        session_id=1,
        lesson_slug=lesson_slug,
        task_id=task_id,
        attempt_no=attempt_no,
        status=status,
        verdict=verdict,
        code=code,
        actual="表达式为假",
        assertions=assertions,
        created_time=datetime.now(timezone.utc),
    )
    db_session.add(row)
    await db_session.flush()
    return row


def _resolver(db_session) -> AgentEvidenceResolver:
    return AgentEvidenceResolver(workspace_repo=WorkspaceReadRepository(db_session))


async def test_assertion_failed_evidence_carries_actual(db_session):
    await _attempt(db_session)

    evidence = await _resolver(db_session).resolve(VISITOR, lesson_slug=LESSON)

    assert evidence.state == "verification_failed"
    assert evidence.source == "workspace"
    assert evidence.verdict == "assertion_failed"
    assert evidence.attempt_no == 1
    # 失败断言排在最前，并带上实际值
    assert evidence.assertions[0].assertion_id == "t1-rows"
    assert "实际值：False" in (evidence.assertions[0].actual or "")
    # 任务进度来自内容定义，与真实通过记录对齐
    assert (evidence.tasks_passed, evidence.tasks_total) == (0, 2)
    assert evidence.current_task_id == "t1"
    assert evidence.lesson_completed is False


async def test_execution_failed_verdict_is_not_assertion_failure(db_session):
    await _attempt(
        db_session,
        status="failed",
        verdict="execution_failed",
        assertions="[]",
    )

    evidence = await _resolver(db_session).resolve(VISITOR, lesson_slug=LESSON)

    assert evidence.state == "execution_failed"
    assert derive_next_action(evidence) == "retry_exercise"
    # 断言未求值时不编造断言结果
    assert evidence.assertions == []


async def test_passed_task_points_to_next_task(db_session):
    await _attempt(
        db_session,
        task_id="t1",
        status="passed",
        verdict="passed",
        assertions="[]",
    )

    evidence = await _resolver(db_session).resolve(VISITOR, lesson_slug=LESSON)

    assert evidence.state == "passed_unconfirmed"
    assert evidence.lesson_completed is False
    assert evidence.tasks_passed == 1
    feedback = build_teaching_feedback(evidence)
    assert feedback.next_action == "next_task"


async def test_all_tasks_passed_marks_lesson_completed(db_session):
    for task_id in ("t1", "t2"):
        await _attempt(
            db_session,
            task_id=task_id,
            status="passed",
            verdict="passed",
            assertions="[]",
        )

    evidence = await _resolver(db_session).resolve(VISITOR, lesson_slug=LESSON)

    assert evidence.lesson_completed is True
    assert evidence.tasks_passed == 2
    assert evidence.current_task_id is None
    assert derive_next_action(evidence) == "inspect_result"


async def test_no_attempt_reports_task_progress_only(db_session):
    evidence = await _resolver(db_session).resolve(VISITOR, lesson_slug=LESSON)

    assert evidence.state == "no_evidence"
    assert evidence.attempt_id is None
    # 没有任何提交也要能说清"现在该做第几个任务"
    assert (evidence.tasks_passed, evidence.tasks_total) == (0, 2)
    assert evidence.current_task_id == "t1"


async def test_task_id_scopes_which_attempt_is_reported(db_session):
    await _attempt(db_session, task_id="t1", attempt_no=2)
    await _attempt(
        db_session,
        task_id="t2",
        attempt_no=1,
        status="passed",
        verdict="passed",
        assertions="[]",
    )

    evidence = await _resolver(db_session).resolve(
        VISITOR, lesson_slug=LESSON, task_id="t2"
    )

    assert evidence.task_id == "t2"
    assert evidence.state == "passed_unconfirmed"


async def test_attempt_id_of_other_visitor_is_ignored(db_session):
    intruder = await _attempt(db_session, visitor=OTHER_VISITOR)

    evidence = await _resolver(db_session).resolve(
        VISITOR, lesson_slug=LESSON, attempt_id=intruder.id
    )

    # 别人的提交读不到，也没有自己的提交 -> 无证据
    assert evidence.state == "no_evidence"
    assert evidence.attempt_id is None


async def test_attempt_id_of_other_lesson_is_ignored(db_session):
    foreign = await _attempt(db_session, lesson_slug=OTHER_LESSON)

    evidence = await _resolver(db_session).resolve(
        VISITOR, lesson_slug=LESSON, attempt_id=int(foreign.id)
    )

    assert evidence.state == "no_evidence"
    assert evidence.lesson_slug == LESSON


@pytest.mark.parametrize(
    "verdict,status,expected",
    [
        ("passed", "passed", "passed_unconfirmed"),
        ("assertion_failed", "failed", "verification_failed"),
        ("execution_failed", "failed", "execution_failed"),
        ("execution_failed", "skipped", "execution_failed"),
        (None, "skipped", "unverifiable"),
        (None, "failed", "verification_failed"),
        (None, None, "no_evidence"),
    ],
)
def test_workspace_state_derivation(verdict, status, expected):
    assert derive_workspace_state(verdict, status) == expected


async def test_evidence_block_lists_failed_assertions(db_session):
    await _attempt(db_session)

    evidence = await _resolver(db_session).resolve(VISITOR, lesson_slug=LESSON)
    block = build_evidence_block(evidence)

    assert "服务端任务证据" in block
    assert "任务进度：0/2 已通过" in block
    assert "当前未通过的任务：t1" in block
    assert "t1-rows" in block
    assert "实际值：表达式 'region_stats.height == 4' 为假" in block


async def test_evidence_block_hides_long_stdout(db_session):
    """证据块不注入完整代码，长文本被截断。"""
    await _attempt(db_session, assertions="[]")

    evidence = await _resolver(db_session).resolve(VISITOR, lesson_slug=LESSON)
    block = build_evidence_block(evidence)

    assert "import polars as pl" not in block


async def test_editor_code_matching_submission_is_neutral(db_session):
    await _attempt(db_session, assertions="[]", code="import polars as pl")

    evidence = await _resolver(db_session).resolve(
        VISITOR, lesson_slug=LESSON, editor_code="  import polars as pl  "
    )

    assert evidence.code_matches_editor is True
    assert "编辑器里的代码不是最近一次提交的代码" not in build_evidence_block(evidence)


async def test_stale_editor_code_is_flagged_in_prompt(db_session):
    """改了代码但没提交时，证据块必须提醒模型别拿旧代码反驳断言结果。"""
    row = await _attempt(
        db_session, status="passed", verdict="passed", assertions="[]"
    )
    row.code = "import polars as pl\nregion_stats = clean()\n"
    await db_session.flush()

    evidence = await _resolver(db_session).resolve(
        VISITOR, lesson_slug=LESSON, editor_code="import polars as pl  # 还在改"
    )

    assert evidence.code_matches_editor is False
    block = build_evidence_block(evidence)
    assert "编辑器里的代码不是最近一次提交的代码" in block


async def test_code_match_is_unknown_without_editor_code(db_session):
    await _attempt(db_session, assertions="[]")

    evidence = await _resolver(db_session).resolve(VISITOR, lesson_slug=LESSON)

    assert evidence.code_matches_editor is None