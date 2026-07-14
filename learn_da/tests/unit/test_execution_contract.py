from uuid import UUID

import pytest
from pydantic import ValidationError

from app.playground.schemas import ExecuteCodeRequest, ExecuteCodeResponse
from app.sandbox import schemas as sandbox_schemas


REQUEST_ID = UUID("00000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000002")


def test_runner_execution_request_accepts_client_request_id_and_agent_source():
    request = sandbox_schemas.RunnerExecutionRequest(
        request_id=REQUEST_ID,
        code="print('ok')",
        source="agent_suggested",
    )

    assert request.request_id == REQUEST_ID
    assert request.source == "agent_suggested"


def test_sandbox_execution_result_serializes_camel_case_wire_aliases():
    result = sandbox_schemas.SandboxExecutionResult(
        request_id=REQUEST_ID,
        execution_id=EXECUTION_ID,
        status="success",
        stdout="ok\n",
        duration_ms=2,
    )

    assert result.model_dump(mode="json", by_alias=True) == {
        "requestId": str(REQUEST_ID),
        "executionId": str(EXECUTION_ID),
        "status": "success",
        "stdout": "ok\n",
        "stderr": "",
        "errorType": None,
        "durationMs": 2,
        "outputTruncated": False,
    }


@pytest.mark.parametrize(
    ("payload", "model"),
    [
        (
            {
                "request_id": REQUEST_ID,
                "code": "print('ok')",
                "source": "operator",
            },
            "RunnerExecutionRequest",
        ),
        (
            {
                "request_id": REQUEST_ID,
                "execution_id": EXECUTION_ID,
                "status": "mocked",
                "duration_ms": 0,
            },
            "SandboxExecutionResult",
        ),
    ],
)
def test_runner_contract_rejects_invalid_source_and_status(payload, model):
    with pytest.raises(ValidationError):
        getattr(sandbox_schemas, model)(**payload)


def test_public_execution_models_serialize_only_the_stable_contract():
    request = ExecuteCodeRequest(
        request_id=REQUEST_ID,
        code="print('ok')",
        source="agent_suggested",
    )
    response = ExecuteCodeResponse(
        request_id=REQUEST_ID,
        execution_id=EXECUTION_ID,
        source="agent_suggested",
        status="rejected",
        stdout="",
        stderr="",
        error_type="unsafe_code",
        duration_ms=0,
    )

    assert request.model_dump(by_alias=True)["requestId"] == REQUEST_ID
    assert request.model_dump(by_alias=True)["source"] == "agent_suggested"
    assert response.model_dump(by_alias=True) == {
        "requestId": REQUEST_ID,
        "executionId": EXECUTION_ID,
        "source": "agent_suggested",
        "status": "rejected",
        "stdout": "",
        "stderr": "",
        "errorType": "unsafe_code",
        "durationMs": 0,
        "outputTruncated": False,
        "resultType": "text",
        "dataframe": None,
    }
    assert "mocked" not in response.model_dump(by_alias=True).values()
    assert "usedSandbox" not in response.model_dump(by_alias=True)
