"""
阶段 1 §5.4：重算脚本测试

覆盖场景：
- 从事件流重放推导完成状态（complete -> uncomplete -> complete）
- 重复完成事件去重，最终状态只取决于序列
- code_run 的 success/error 计数依据 status 字段
- 五次成功运行不会被解释为失败
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.analytics.models import LearningRecord
from app.learner_state.models import LearnerLessonProgress
from scripts.recompute_learner_state import _derive_state, recompute


def _ts(minutes_ago: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)


def test_derive_state_complete_uncomplete_complete():
    """complete -> uncomplete -> complete 最终应为 completed"""
    records = [
        LearningRecord(
            visitor_id="v1",
            event_type="lesson_complete",
            lesson_slug="polars-basics",
            created_time=_ts(60),
        ),
        LearningRecord(
            visitor_id="v1",
            event_type="lesson_uncomplete",
            lesson_slug="polars-basics",
            created_time=_ts(30),
        ),
        LearningRecord(
            visitor_id="v1",
            event_type="lesson_complete",
            lesson_slug="polars-basics",
            created_time=_ts(10),
        ),
    ]
    derived = _derive_state(records)
    assert derived["status"] == "completed"
    assert derived["completed_at"] == records[-1].created_time


def test_derive_state_duplicate_completes_dedup():
    """重复 complete 事件不应改变最终状态，completed_at 取最后一次"""
    records = [
        LearningRecord(
            visitor_id="v1",
            event_type="lesson_complete",
            lesson_slug="polars-basics",
            created_time=_ts(60),
        ),
        LearningRecord(
            visitor_id="v1",
            event_type="lesson_complete",
            lesson_slug="polars-basics",
            created_time=_ts(50),
        ),
        LearningRecord(
            visitor_id="v1",
            event_type="lesson_complete",
            lesson_slug="polars-basics",
            created_time=_ts(40),
        ),
    ]
    derived = _derive_state(records)
    assert derived["status"] == "completed"
    # 仍然只有一次有效完成语义，completed_at 取最新
    assert derived["completed_at"] == records[-1].created_time


def test_derive_state_code_run_success_not_counted_as_failure():
    """五次成功运行不应被解释为失败"""
    records = [
        LearningRecord(
            visitor_id="v1",
            event_type="code_run",
            lesson_slug="polars-basics",
            status="success",
            created_time=_ts(50),
        )
        for _ in range(5)
    ]
    derived = _derive_state(records)
    assert derived["attempt_count"] == 5
    assert derived["success_count"] == 5
    assert derived["error_count"] == 0
    assert derived["status"] == "started"


def test_derive_state_code_run_error_aggregation():
    """error/timeout/rejected 都计入失败侧，可聚合"""
    records = [
        LearningRecord(
            visitor_id="v1",
            event_type="code_run",
            lesson_slug="polars-basics",
            status="success",
            created_time=_ts(30),
        ),
        LearningRecord(
            visitor_id="v1",
            event_type="code_run",
            lesson_slug="polars-basics",
            status="error",
            created_time=_ts(20),
        ),
        LearningRecord(
            visitor_id="v1",
            event_type="code_run",
            lesson_slug="polars-basics",
            status="timeout",
            created_time=_ts(10),
        ),
    ]
    derived = _derive_state(records)
    assert derived["attempt_count"] == 3
    assert derived["success_count"] == 1
    assert derived["error_count"] == 2


@pytest.mark.anyio
async def test_recompute_upserts_from_events(db_session):
    """recompute 应从 learning_records 重放并 upsert learner_lesson_progress"""
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            LearningRecord(
                visitor_id="v-recompute",
                event_type="lesson_start",
                lesson_slug="polars-basics",
                created_time=now - timedelta(minutes=60),
            ),
            LearningRecord(
                visitor_id="v-recompute",
                event_type="code_run",
                lesson_slug="polars-basics",
                status="success",
                created_time=now - timedelta(minutes=50),
            ),
            LearningRecord(
                visitor_id="v-recompute",
                event_type="code_run",
                lesson_slug="polars-basics",
                status="error",
                created_time=now - timedelta(minutes=40),
            ),
            LearningRecord(
                visitor_id="v-recompute",
                event_type="lesson_complete",
                lesson_slug="polars-basics",
                created_time=now - timedelta(minutes=30),
            ),
        ]
    )
    await db_session.flush()

    # 注意：test_engine 为 session 级内存库，其他测试提交的记录也可能可见，
    # 因此只断言本测试使用的 v-recompute 分组，而非全局计数。
    audit = await recompute(write=False, session=db_session)
    detail = next(
        d
        for d in audit["details"]
        if d["visitor_id"] == "v-recompute" and d["lesson_slug"] == "polars-basics"
    )
    assert detail["status"] == "completed"
    assert detail["attempt_count"] == 2
    assert detail["success_count"] == 1
    assert detail["error_count"] == 1

    # 行已 upsert 到会话中，通过 select 验证
    from sqlalchemy import select

    stmt = select(LearnerLessonProgress).where(
        LearnerLessonProgress.visitor_id == "v-recompute",
        LearnerLessonProgress.lesson_slug == "polars-basics",
    )
    result = await db_session.execute(stmt)
    row = result.scalar_one()
    assert row.status == "completed"
    assert row.attempt_count == 2
    assert row.success_count == 1
    assert row.error_count == 1
