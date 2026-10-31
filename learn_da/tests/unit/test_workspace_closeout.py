import asyncio
import pytest
from sqlalchemy import func, select
from app.workspace.models import HintUsage, TaskAttempt
from tests.unit.test_workspace_api import _create, _runner, _payload, _assertion

pytestmark = pytest.mark.anyio


async def test_same_request_id_run_then_submit_records_attempt(client, db_session):
    data = await _create(client)
    runner = await _runner(client)
    runner.execute_session.return_value = _payload(cells=['c1', 'c2'], stop_at='c2', assertions=[_assertion('passed')])
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    await client.post(root + '/cells/c2/run', json={'requestId': 'shared'})
    result = await client.post(root + '/tasks/t1/submit', json={'requestId': 'shared'})
    assert result.json()['data']['taskStatus'] == 'passed'
    assert (await db_session.execute(select(func.count()).select_from(TaskAttempt))).scalar() == 1
    assert runner.execute_session.await_count == 2


async def test_hint_retry_returns_identical_response_and_counts_once(client, db_session):
    data = await _create(client)
    url = f"/api/v1/workspace/sessions/{data['sessionId']}/tasks/t1/hint"
    first = await client.post(url, json={'requestId': 'hint-retry'})
    second = await client.post(url, json={'requestId': 'hint-retry'})
    assert first.json()['data'] == second.json()['data']
    assert (await db_session.execute(select(func.count()).select_from(HintUsage))).scalar() == 1


async def test_edit_during_run_keeps_new_code_stale(client):
    data = await _create(client)
    runner = await _runner(client)
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    async def execute(_):
        await client.put(root + '/cells/c1', json={'code': '# edited during execution'})
        return _payload(cells=['c1', 'c2'], stop_at='c2', assertions=[_assertion('passed')])
    runner.execute_session.side_effect = execute
    await client.post(root + '/tasks/t1/submit', json={'requestId': 'edit-race'})
    snapshot = (await client.get(root)).json()['data']
    assert snapshot['cells'][0]['code'] == '# edited during execution'
    assert snapshot['cells'][0]['status'] == 'stale'
    assert snapshot['cells'][1]['status'] == 'stale'


async def test_workspace_events_restore_learning_projection_and_replay_is_idempotent(client, db_session):
    from app.learner_state.service import LearnerStateService
    from app.analytics.models import LearningRecord
    data = await _create(client)
    from app.workspace.models import LessonSession
    session = (await db_session.execute(select(LessonSession).where(LessonSession.id == data['sessionId']))).scalar_one()
    visitor = session.visitor_id
    runner = await _runner(client)
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    for task, cell in [('t1', 'c2'), ('t2', 'c3')]:
        runner.execute_session.return_value = _payload(cells=['c1', 'c2'] + (['c3'] if cell == 'c3' else []), stop_at=cell, assertions=[_assertion('passed')])
        await client.post(root + f'/tasks/{task}/submit', json={'requestId': task})
        await client.post(root + f'/tasks/{task}/submit', json={'requestId': task})
    progress = await LearnerStateService(db_session).get_lesson_progress(visitor, 'polars-groupby')
    assert progress.status == 'completed'
    assert progress.attempt_count == 2
    counts = dict((await db_session.execute(select(LearningRecord.event_type, func.count()).where(LearningRecord.visitor_id == visitor).group_by(LearningRecord.event_type))).all())
    assert counts == {'lesson_start': 1, 'code_run': 2, 'lesson_complete': 1}
    await client.put(root + '/cells/c2', json={'code': '# edit completed lesson'})
    progress = await LearnerStateService(db_session).get_lesson_progress(visitor, 'polars-groupby')
    assert progress.status == 'uncompleted'


async def test_concurrent_requests_on_separate_connections_replay_once(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.database.base import Base
    from app.workspace.service import WorkspaceService
    from unittest.mock import AsyncMock
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "concurrent.db"}')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    runner = AsyncMock()
    runner.execute_session.return_value = _payload(cells=['c1', 'c2'], stop_at='c2', assertions=[_assertion('passed')])
    async def create():
        async with sessions() as db:
            item, _ = await WorkspaceService(db, runner).get_or_create('concurrent-visitor', 'polars-groupby')
            return item.id
    try:
        ids = await asyncio.gather(create(), create())
        assert ids[0] == ids[1]
        async def submit():
            async with sessions() as db:
                return await WorkspaceService(db, runner).submit_task('concurrent-visitor', ids[0], 't1', 'retry')
        first, second = await asyncio.gather(submit(), submit())
        assert first.model_dump() == second.model_dump()
        assert runner.execute_session.await_count == 1
        async def hint():
            async with sessions() as db:
                return await WorkspaceService(db, runner).request_hint('concurrent-visitor', ids[0], 't1', 'hint-retry')
        first_hint, second_hint = await asyncio.gather(hint(), hint())
        assert first_hint.model_dump() == second_hint.model_dump()
        async with sessions() as db:
            assert (await db.execute(select(func.count()).select_from(TaskAttempt))).scalar() == 1
            assert (await db.execute(select(func.count()).select_from(HintUsage))).scalar() == 1
    finally:
        await engine.dispose()


async def test_default_and_application_limits_are_enforced(monkeypatch):
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from slowapi import Limiter
    import app.utils.limiter as module
    app = FastAPI()
    limiter = Limiter(key_func=module._trusted_key_func, default_limits=['1/minute'], application_limits=['2/minute'])
    monkeypatch.setattr(module, 'limiter', limiter)
    module.setup_limiter_middleware(app)
    @app.get('/one')
    async def one():
        return {'ok': True}
    @app.get('/two')
    async def two():
        return {'ok': True}
    @app.get('/three')
    async def three():
        return {'ok': True}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://limits') as client:
        assert (await client.get('/one')).status_code == 200
        assert (await client.get('/one')).status_code == 429
        # The rejected attempt consumes the shared application budget too.
        assert (await client.get('/three')).status_code == 429


def test_hint_migration_preserves_existing_history():
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[2] / 'migrations/versions/c7d31a8e9f02_hint_request_id.py'
    spec = importlib.util.spec_from_file_location('hint_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    try:
        with engine.begin() as db:
            db.exec_driver_sql('CREATE TABLE hint_usages (id INTEGER PRIMARY KEY, visitor_id VARCHAR(64), content TEXT)')
            db.exec_driver_sql("INSERT INTO hint_usages VALUES (1, 'visitor', 'existing hint')")
            migration.op = Operations(MigrationContext.configure(db))
            migration.upgrade()
            assert db.exec_driver_sql('SELECT content, request_id, response FROM hint_usages').one() == ('existing hint', None, None)
            assert any(item['name'] == 'uq_hint_visitor_request' for item in sa.inspect(db).get_unique_constraints('hint_usages'))
            migration.downgrade()
            assert db.exec_driver_sql('SELECT content FROM hint_usages').scalar() == 'existing hint'
    finally:
        engine.dispose()


async def test_separate_connection_edit_completes_while_runner_is_waiting(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.database.base import Base
    from app.workspace.service import WorkspaceService
    from unittest.mock import AsyncMock
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "edit-race.db"}')
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    started, release = asyncio.Event(), asyncio.Event()
    executing_db = None
    async def execute(_):
        assert not executing_db.in_transaction(), "read connection retained during Runner call"
        started.set()
        await release.wait()
        return _payload(cells=['c1', 'c2'], stop_at='c2', assertions=[_assertion('passed')])
    runner = AsyncMock()
    runner.execute_session.side_effect = execute
    try:
        async with sessions() as db:
            item, _ = await WorkspaceService(db, runner).get_or_create('editor', 'polars-groupby')
            session_id = item.id
        async def submit():
            nonlocal executing_db
            async with sessions() as db:
                executing_db = db
                return await WorkspaceService(db, runner).submit_task('editor', session_id, 't1', 'edit-race')
        pending = asyncio.create_task(submit())
        await started.wait()
        async with sessions() as db:
            await asyncio.wait_for(WorkspaceService(db, runner).update_cell('editor', session_id, 'c1', '# latest edit'), timeout=2)
        release.set()
        await pending
        async with sessions() as db:
            snapshot = await WorkspaceService(db, runner).snapshot('editor', session_id)
            assert snapshot.cells[0].code == '# latest edit'
            assert snapshot.cells[0].status == snapshot.cells[1].status == 'stale'
            attempt = (await db.execute(select(TaskAttempt))).scalar_one()
            assert attempt.code != '# latest edit'
    finally:
        release.set()
        await engine.dispose()


async def test_progress_and_report_exclude_stale_passes_but_keep_attempt_history(client, db_session):
    data = await _create(client)
    runner = await _runner(client)
    root = f"/api/v1/workspace/sessions/{data['sessionId']}"
    runner.execute_session.return_value = _payload(cells=['c1', 'c2'], stop_at='c2', assertions=[_assertion('passed')])
    await client.post(root + '/tasks/t1/submit', json={'requestId': 'pass-before-edit'})
    await client.put(root + '/cells/c2', json={'code': '# changed'})
    for endpoint, rows_key in [('progress', 'lessons'), ('report', 'lessonProgress')]:
        result = (await client.get('/api/v1/workspace/' + endpoint)).json()['data']
        lesson = next(row for row in result[rows_key] if row['lessonSlug'] == 'polars-groupby')
        assert lesson['passedTasks'] == 0
        assert lesson['currentTaskId'] == 't1'
        assert result['summary']['tasksAttempted'] == 1
        assert result['summary']['attemptsTotal'] == 1
    assert (await db_session.execute(select(TaskAttempt.status))).scalar_one() == 'passed'
    from app.workspace.models import LessonSession
    from app.workspace.repository import WorkspaceReadRepository
    from app.agent.evidence import AgentEvidenceResolver
    session = (await db_session.execute(select(LessonSession).where(LessonSession.id == data['sessionId']))).scalar_one()
    evidence = await AgentEvidenceResolver(WorkspaceReadRepository(db_session)).resolve(session.visitor_id, 'polars-groupby')
    assert evidence.state == 'unverifiable'
    assert evidence.requires_recheck is True


async def test_hint_snapshot_query_count_is_constant(db_session):
    from sqlalchemy import event
    from app.workspace.repository import WorkspaceReadRepository
    statements = []
    def count_statement(state):
        statements.append(state)
    db_session.add(HintUsage(visitor_id='query-visitor', session_id=99, lesson_slug='polars-groupby', task_id='t1', level=1, content='hint'))
    await db_session.flush()
    event.listen(db_session.sync_session, 'do_orm_execute', count_statement)
    try:
        states = await WorkspaceReadRepository(db_session).hint_states('query-visitor', 'polars-groupby', ['t1', 't2', 't3'])
    finally:
        event.remove(db_session.sync_session, 'do_orm_execute', count_statement)
    assert states['t1'].hints_used == 1
    assert len(statements) == 2
