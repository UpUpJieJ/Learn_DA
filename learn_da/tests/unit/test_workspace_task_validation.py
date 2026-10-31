"""Execution success must not resurrect invalidated task validation."""
import pytest
from sqlalchemy import select
from app.workspace.models import LessonSession, TaskAttempt
from app.workspace.repository import WorkspaceReadRepository
from app.agent.evidence import AgentEvidenceResolver
from tests.unit.test_workspace_api import _create, _runner, _payload, _assertion

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def disable_rate_limit_for_validation_tests(monkeypatch):
    from app.utils.limiter import limiter
    monkeypatch.setattr(limiter, 'enabled', False)


async def _passed(client, root, runner, task, cell, request):
    runner.execute_session.return_value = _payload(
        cells=['c1', 'c2'] + (['c3'] if cell == 'c3' else []),
        stop_at=cell, assertions=[_assertion('passed')])
    await client.post(root + f'/tasks/{task}/submit', json={'requestId': request})


@pytest.mark.parametrize('upstream', [False, True])
async def test_execution_cannot_restore_invalidated_task_validation(client, db_session, upstream):
    data = await _create(client)
    runner = await _runner(client)
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    await _passed(client, root, runner, 't1', 'c2', 'first-pass')
    edited = 'c1' if upstream else 'c2'
    await client.put(root + f'/cells/{edited}', json={'code': '# edited'})
    if upstream:
        await _passed(client, root, runner, 't2', 'c3', 'downstream-submit')
    else:
        await client.post(root + '/cells/c2/run', json={'requestId': 'plain-run'})
    snapshot = (await client.get(root)).json()['data']
    assert snapshot['cells'][1]['status'] == 'ok'
    assert snapshot['tasks'][0]['status'] == 'todo'
    for endpoint, key in [('progress', 'lessons'), ('report', 'lessonProgress')]:
        result = (await client.get('/api/v1/workspace/' + endpoint)).json()['data']
        lesson = next(row for row in result[key] if row['lessonSlug'] == 'polars-groupby')
        assert lesson['passedTasks'] == (1 if upstream else 0)
        assert lesson['currentTaskId'] == 't1'
    session = (await db_session.execute(select(LessonSession).where(LessonSession.id == data['sessionId']))).scalar_one()
    repo = WorkspaceReadRepository(db_session)
    assert 't1' not in await repo.passed_task_ids(session.visitor_id, session.lesson_slug)
    evidence = await AgentEvidenceResolver(repo).resolve(session.visitor_id, session.lesson_slug, task_id='t1')
    assert evidence.state == 'unverifiable'
    assert evidence.requires_recheck
    original = (await db_session.execute(select(TaskAttempt).where(TaskAttempt.task_id == 't1'))).scalar_one()
    assert original.status == 'passed'


async def test_unchanged_downstream_submit_preserves_upstream_validation(client):
    data = await _create(client)
    runner = await _runner(client)
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    await _passed(client, root, runner, 't1', 'c2', 'first-pass')
    await _passed(client, root, runner, 't2', 'c3', 'next-pass')
    snapshot = (await client.get(root)).json()['data']
    assert [task['status'] for task in snapshot['tasks']] == ['passed', 'passed']


async def test_resubmitting_current_task_restores_validation(client):
    data = await _create(client)
    runner = await _runner(client)
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    await _passed(client, root, runner, 't1', 'c2', 'first-pass')
    await client.put(root + '/cells/c2', json={'code': '# corrected'})
    await _passed(client, root, runner, 't1', 'c2', 'verified-again')
    snapshot = (await client.get(root)).json()['data']
    assert snapshot['tasks'][0]['status'] == 'passed'


async def test_edit_clears_validation_even_when_execution_status_already_stale(client, db_session):
    from app.workspace.models import SessionCell
    data = await _create(client)
    cell = (await db_session.execute(select(SessionCell).where(
        SessionCell.session_id == data['sessionId'], SessionCell.cell_id == 'c2'))).scalar_one()
    cell.task_verified = True
    cell.status = 'stale'
    await db_session.flush()
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    await client.put(root + '/cells/c1', json={'code': '# upstream edit'})
    await db_session.refresh(cell)
    assert cell.task_verified is False


@pytest.mark.parametrize('verdict', ['assertion_failed', 'execution_failed'])
async def test_unsuccessful_submission_clears_current_validation(client, db_session, verdict):
    from app.workspace.models import SessionCell
    data = await _create(client)
    runner = await _runner(client)
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    await _passed(client, root, runner, 't1', 'c2', 'initial-pass')
    result = _payload(cells=['c1', 'c2'], stop_at='c2', verdict=verdict, assertions=[_assertion('failed')])
    if verdict == 'execution_failed':
        result['cells'][0]['status'] = 'error'
        result['cells'][1]['status'] = 'skipped'
    runner.execute_session.return_value = result
    await client.post(root + '/tasks/t1/submit', json={'requestId': 'failed-recheck'})
    marker = (await db_session.execute(select(SessionCell.task_verified).where(
        SessionCell.session_id == data['sessionId'], SessionCell.cell_id == 'c2'))).scalar_one()
    assert marker is False


def test_migration_requires_resubmit_without_rewriting_historical_attempts():
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[2] / 'migrations/versions/d8a42b6f9013_task_verified.py'
    spec = importlib.util.spec_from_file_location('validation_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    try:
        with engine.begin() as db:
            db.exec_driver_sql('CREATE TABLE session_cells (id INTEGER PRIMARY KEY, status TEXT)')
            db.exec_driver_sql("INSERT INTO session_cells VALUES (1, 'ok')")
            db.exec_driver_sql('CREATE TABLE task_attempts (id INTEGER PRIMARY KEY, status TEXT)')
            db.exec_driver_sql("INSERT INTO task_attempts VALUES (1, 'passed')")
            migration.op = Operations(MigrationContext.configure(db))
            migration.upgrade()
            assert db.exec_driver_sql('SELECT status, task_verified FROM session_cells').one() == ('ok', False)
            assert db.exec_driver_sql('SELECT status FROM task_attempts').scalar() == 'passed'
            migration.downgrade()
            assert db.exec_driver_sql('SELECT status FROM session_cells').scalar() == 'ok'
    finally:
        engine.dispose()


@pytest.mark.parametrize('edit', [True, False])
async def test_late_result_cannot_overwrite_a_newer_verified_submission(tmp_path, edit):
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from unittest.mock import AsyncMock
    from app.core.database.base import Base
    from app.workspace.service import WorkspaceService, _scoped_key
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "out-of-order.db"}')
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    started, release = asyncio.Event(), asyncio.Event()
    old_runner, new_runner = AsyncMock(), AsyncMock()
    async def old_execute(_):
        started.set()
        await release.wait()
        result = _payload(cells=['c1', 'c2'], stop_at='c2', verdict='execution_failed', assertions=[_assertion('failed')])
        result['cells'][1]['status'] = 'error'
        return result
    old_runner.execute_session.side_effect = old_execute
    new_runner.execute_session.return_value = _payload(cells=['c1', 'c2'], stop_at='c2', assertions=[_assertion('passed')])
    try:
        async with sessions() as db:
            session, spec = await WorkspaceService(db, new_runner).get_or_create('parallel', 'polars-groupby')
            session_id = session.id
        async def old_submit():
            # Bypass only the process-local mutex to model another worker process;
            # all SQL sessions, savepoints and production persistence are real.
            async with sessions() as db:
                service = WorkspaceService(db, old_runner)
                from types import SimpleNamespace
                session = SimpleNamespace(id=session_id, lesson_slug='polars-groupby', visitor_id='parallel')
                result = await service._run_once('parallel', session, spec, 'c2', 'old',
                    task=spec.task('t1'), record_attempt=True,
                    key=_scoped_key(session_id, 'submit', 't1', 'old'))
                await service._commit()
                return result
        pending = asyncio.create_task(old_submit())
        await started.wait()
        async with sessions() as db:
            service = WorkspaceService(db, new_runner)
            if edit:
                await service.update_cell('parallel', session_id, 'c2', '# new corrected version')
            await service.submit_task('parallel', session_id, 't1', 'new')
        release.set()
        await pending
        async with sessions() as db:
            service = WorkspaceService(db, new_runner)
            snapshot = await service.snapshot('parallel', session_id)
            assert snapshot.tasks[0].status == 'passed'
            assert snapshot.cells[1].status == 'ok'
            evidence = await AgentEvidenceResolver(WorkspaceReadRepository(db)).resolve('parallel', 'polars-groupby', task_id='t1')
            assert evidence.state == 'passed_unconfirmed'
            attempts = list((await db.execute(select(TaskAttempt).order_by(TaskAttempt.id))).scalars())
            assert len(attempts) == 2
            assert attempts[0].status == 'passed' and attempts[1].status == 'failed'
            assert attempts[1].created_time < attempts[0].created_time
    finally:
        release.set()
        await engine.dispose()


@pytest.mark.parametrize('cause', ['migration', 'execution'])
async def test_invalid_live_validation_revokes_completed_projection_idempotently(client, db_session, cause):
    from sqlalchemy import func
    from app.workspace.models import SessionCell
    from app.analytics.models import LearningRecord
    from app.learner_state.service import LearnerStateService
    data = await _create(client)
    runner = await _runner(client)
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    await _passed(client, root, runner, 't1', 'c2', 'pass-one')
    await _passed(client, root, runner, 't2', 'c3', 'pass-two')
    session = (await db_session.execute(select(LessonSession).where(LessonSession.id == data['sessionId']))).scalar_one()
    learner = LearnerStateService(db_session)
    assert (await learner.get_lesson_progress(session.visitor_id, session.lesson_slug)).status == 'completed'
    if cause == 'migration':
        for cell in (await db_session.execute(select(SessionCell).where(SessionCell.session_id == session.id))).scalars():
            cell.task_verified = False
        await db_session.flush()
        await _create(client)
        await _create(client)
    else:
        runner.execute_session.return_value = _payload(cells=['c1'], stop_at='c1')
        await client.post(root + '/cells/c1/run', json={'requestId': 'invalidate-execution'})
        await client.post(root + '/cells/c1/run', json={'requestId': 'invalidate-execution'})
    assert (await learner.get_lesson_progress(session.visitor_id, session.lesson_slug)).status == 'uncompleted'
    assert (await db_session.execute(select(func.count()).select_from(LearningRecord).where(
        LearningRecord.visitor_id == session.visitor_id, LearningRecord.event_type == 'lesson_uncomplete'))).scalar() == 1
