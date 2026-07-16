from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.playground.schemas import ExecuteCodeRequest
from app.playground.service import PlaygroundService
from app.sandbox.schemas import SandboxExecutionResult


REQUEST_ID = UUID("00000000-0000-0000-0000-000000000001")
RESULT_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000002")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000003")


def _make_service(result: SandboxExecutionResult) -> tuple[PlaygroundService, AsyncMock]:
    runner_mock = AsyncMock()
    runner_mock.execute = AsyncMock(return_value=result)
    from app.sandbox.service import SandboxService
    sandbox_service = SandboxService(runner_client=runner_mock)
    service = PlaygroundService(sandbox_service=sandbox_service)
    return service, runner_mock


@pytest.mark.unit
async def test_execute_parses_dataframe_marker_and_cleans_stdout():
    result = SandboxExecutionResult(
        status="success",
        stdout=(
            "before\n"
            '__LEARN_DA_DATAFRAME__{"columns":["name","score"],'
            '"rows":[{"name":"Alice","score":95}],'
            '"rowCount":1,"truncated":false}\n'
            "after\n"
        ),
        stderr="",
        duration_ms=12,
    )
    service, _ = _make_service(result)

    resp = await service.execute(ExecuteCodeRequest(code="df = make_df()"))

    assert resp.result_type == "dataframe"
    assert resp.dataframe is not None
    assert resp.dataframe.columns == ["name", "score"]
    assert resp.dataframe.rows == [{"name": "Alice", "score": 95}]
    assert resp.dataframe.row_count == 1
    assert resp.stdout == "before\nafter\n"


@pytest.mark.unit
async def test_execute_marks_error_results_as_error_type():
    result = SandboxExecutionResult(
        status="error",
        stdout="",
        stderr="NameError: name 'df' is not defined",
        duration_ms=4,
    )
    service, _ = _make_service(result)

    resp = await service.execute(ExecuteCodeRequest(code="print(df)"))

    assert resp.result_type == "error"
    assert resp.dataframe is None


@pytest.mark.unit
async def test_execute_forwards_stable_execution_contract_fields():
    result = SandboxExecutionResult(
        request_id=RESULT_REQUEST_ID,
        execution_id=EXECUTION_ID,
        status="error",
        stdout="",
        stderr="NameError: name 'df' is not defined",
        error_type="name_error",
        duration_ms=37,
        output_truncated=True,
    )
    service, _ = _make_service(result)

    resp = await service.execute(
        ExecuteCodeRequest(
            request_id=REQUEST_ID,
            code="print(df)",
            source="agent_suggested",
        )
    )

    assert resp.request_id == REQUEST_ID
    assert resp.execution_id == EXECUTION_ID
    assert resp.source == "agent_suggested"
    assert resp.error_type == "name_error"
    assert resp.duration_ms == 37
    assert resp.output_truncated is True


@pytest.mark.unit
async def test_execute_appends_dataframe_probe_to_user_code():
    result = SandboxExecutionResult(
        status="success",
        stdout="plain output\n",
        stderr="",
        duration_ms=5,
    )
    service, runner_mock = _make_service(result)

    await service.execute(ExecuteCodeRequest(code="print('ok')"))

    # Verify that the runner received code with the dataframe probe.
    call_args = runner_mock.execute.call_args
    request_obj = call_args.args[0]
    submitted_code = request_obj.code if hasattr(request_obj, "code") else str(request_obj)
    assert "print('ok')" in submitted_code
    assert "__LEARN_DA_DATAFRAME__" in submitted_code
    assert "__learn_da_candidates = ('result', 'df')" in submitted_code
