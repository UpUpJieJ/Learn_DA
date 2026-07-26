"""
阶段 1：统一学习事实 - LearnerStateService 单元测试

覆盖场景：
- 完成/撤销/再次完成的状态一致性
- 进度投影正确性（completedLessons、lastVisited、attemptCount）
- code_run 状态记录（success/error 区分）
- 推荐冷却持久化（跨请求有效）
- 幂等性（重复完成不产生副作用）
"""

import pytest

from app.learner_state.service import LearnerStateService


@pytest.mark.anyio
async def test_complete_and_get_completed_lessons(db_session):
    """完成课程后，get_completed_lessons 应返回该课程"""
    svc = LearnerStateService(db_session)

    await svc.complete_lesson("visitor-1", "polars-basics")
    await svc.complete_lesson("visitor-1", "polars-expressions")

    completed = await svc.get_completed_lessons("visitor-1")
    assert set(completed) == {"polars-basics", "polars-expressions"}


@pytest.mark.anyio
async def test_uncomplete_lesson(db_session):
    """撤销完成后，课程不应出现在已完成列表中"""
    svc = LearnerStateService(db_session)

    await svc.complete_lesson("visitor-1", "polars-basics")
    await svc.uncomplete_lesson("visitor-1", "polars-basics")

    completed = await svc.get_completed_lessons("visitor-1")
    assert "polars-basics" not in completed


@pytest.mark.anyio
async def test_recomplete_after_uncomplete(db_session):
    """撤销后再次完成，状态应恢复为 completed"""
    svc = LearnerStateService(db_session)

    await svc.complete_lesson("visitor-1", "polars-basics")
    await svc.uncomplete_lesson("visitor-1", "polars-basics")
    await svc.complete_lesson("visitor-1", "polars-basics")

    completed = await svc.get_completed_lessons("visitor-1")
    assert "polars-basics" in completed

    detail = await svc.get_lesson_progress("visitor-1", "polars-basics")
    assert detail is not None
    assert detail.status == "completed"
    assert detail.completed_at is not None


@pytest.mark.anyio
async def test_complete_is_idempotent(db_session):
    """重复完成同一课程不应产生副作用"""
    svc = LearnerStateService(db_session)

    await svc.complete_lesson("visitor-1", "polars-basics")
    await svc.complete_lesson("visitor-1", "polars-basics")

    completed = await svc.get_completed_lessons("visitor-1")
    assert completed.count("polars-basics") == 1


@pytest.mark.anyio
async def test_full_progress_projection(db_session):
    """完整进度投影应包含正确的完成列表、最近访问和统计"""
    svc = LearnerStateService(db_session)

    await svc.record_lesson_start("visitor-1", "polars-basics")
    await svc.complete_lesson("visitor-1", "polars-basics")
    await svc.record_lesson_start("visitor-1", "polars-expressions")

    summary = await svc.get_full_progress("visitor-1")

    assert summary.total_completed == 1
    assert summary.total_started == 2
    assert "polars-basics" in summary.completed_lessons
    # 最近访问应该是 polars-expressions（最后活动）
    assert summary.last_visited_slug == "polars-expressions"
    assert len(summary.lesson_details) == 2


@pytest.mark.anyio
async def test_record_attempt_success_and_error(db_session):
    """code_run 尝试记录应正确区分 success 和 error"""
    svc = LearnerStateService(db_session)

    await svc.record_attempt("visitor-1", "polars-basics", "success")
    await svc.record_attempt("visitor-1", "polars-basics", "error")
    await svc.record_attempt("visitor-1", "polars-basics", "success")

    detail = await svc.get_lesson_progress("visitor-1", "polars-basics")
    assert detail is not None
    assert detail.attempt_count == 3
    assert detail.success_count == 2
    assert detail.error_count == 1


@pytest.mark.anyio
async def test_last_visited_tracking(db_session):
    """get_last_visited 应返回最近活动的课程"""
    svc = LearnerStateService(db_session)

    await svc.record_lesson_start("visitor-1", "polars-basics")
    await svc.record_lesson_start("visitor-1", "duckdb-intro")

    last = await svc.get_last_visited("visitor-1")
    assert last == "duckdb-intro"


@pytest.mark.anyio
async def test_cooldown_set_and_check(db_session):
    """设置冷却后，is_in_cooldown 应返回 True"""
    svc = LearnerStateService(db_session)

    # 初始无冷却
    assert await svc.is_in_cooldown("visitor-1", "polars-basics") is False

    # 设置 300 秒冷却
    await svc.set_cooldown("visitor-1", "polars-basics", 300)
    assert await svc.is_in_cooldown("visitor-1", "polars-basics") is True

    # 其他课程不受影响
    assert await svc.is_in_cooldown("visitor-1", "polars-expressions") is False


@pytest.mark.anyio
async def test_cooldown_upsert(db_session):
    """重复设置冷却应更新而非重复创建"""
    svc = LearnerStateService(db_session)

    await svc.set_cooldown("visitor-1", "polars-basics", 100)
    await svc.set_cooldown("visitor-1", "polars-basics", 600)

    # 仍然在冷却中
    assert await svc.is_in_cooldown("visitor-1", "polars-basics") is True


@pytest.mark.anyio
async def test_visitor_isolation(db_session):
    """不同 visitor 的状态应完全隔离"""
    svc = LearnerStateService(db_session)

    await svc.complete_lesson("visitor-1", "polars-basics")
    await svc.complete_lesson("visitor-2", "duckdb-intro")

    v1_completed = await svc.get_completed_lessons("visitor-1")
    v2_completed = await svc.get_completed_lessons("visitor-2")

    assert v1_completed == ["polars-basics"]
    assert v2_completed == ["duckdb-intro"]


@pytest.mark.anyio
async def test_lesson_start_creates_progress(db_session):
    """record_lesson_start 应创建 started 状态的进度记录"""
    svc = LearnerStateService(db_session)

    await svc.record_lesson_start("visitor-1", "polars-basics")

    detail = await svc.get_lesson_progress("visitor-1", "polars-basics")
    assert detail is not None
    assert detail.status == "started"
    assert detail.completed_at is None
