import uuid

import pytest
from sqlalchemy import select

from app.analytics.models import LearningRecord
from app.sandbox.schemas import SandboxExecutionResult


@pytest.mark.parametrize("status", ["success", "error", "timeout"])
async def test_lab_execution_records_authoritative_idempotent_event(client, db_session, status):
    from main import app
    request_id = uuid.uuid4()
    app.state.runner_client.execute.return_value = SandboxExecutionResult(
        request_id=request_id, status=status, stdout="", stderr="")
    for _ in range(2):
        response = await client.post("/api/v1/playground/execute", json={"requestId":str(request_id), "code":"x=1"})
        assert response.status_code == 200
    records = list((await db_session.execute(select(LearningRecord).where(LearningRecord.event_type=="code_run"))).scalars())
    assert len(records) == 1
    assert records[0].status == status
    assert records[0].lesson_slug is None


async def test_lab_nonfinite_preview_values_are_json_safe(client):
    import json
    from main import app
    from app.playground.service import DATAFRAME_MARKER
    data={"columns":["x","y"],"rows":[{"x":float('nan'),"y":float('inf')}],"rowCount":1,"truncated":False}
    app.state.runner_client.execute.return_value=SandboxExecutionResult(status="success",stdout=DATAFRAME_MARKER+json.dumps(data),stderr="")
    response=await client.post("/api/v1/playground/execute",json={"code":"x=1"})
    assert response.status_code==200
    assert response.json()['data']['dataframe']['rows']==[{"x":None,"y":"Infinity"}]
