import logging

from app.sandbox.client import RunnerClient, RunnerUnavailableError
from app.sandbox.safety_check import validate_code
from app.sandbox.schemas import ExecutionStatus, SandboxExecutionResult

from fastapi import status
from app.core.exceptions.base_exceptions import BusinessException

log = logging.getLogger(__name__)


class SandboxService:
    """Delegate every execution to the external Runner via RunnerClient."""

    def __init__(self, runner_client: RunnerClient):
        self._client = runner_client

    async def execute(self, code: str, *, request_id=None, source: str = "playground") -> SandboxExecutionResult:
        from uuid import uuid4
        from app.sandbox.schemas import RunnerExecutionRequest

        safety_result = validate_code(code)
        if not safety_result.is_safe:
            raise BusinessException(
                message=safety_result.reason or "代码未通过安全校验",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        payload = RunnerExecutionRequest(
            request_id=request_id or uuid4(),
            code=code,
            source=source,
        )
        result = await self._client.execute(payload)

        # Structured audit log (Spec §3.3 / §5.1).
        log.info(
            "execution_audit",
            extra={
                "request_id": str(result.request_id),
                "execution_id": str(result.execution_id),
                "source": source,
                "status": result.status,
                "error_type": result.error_type,
                "duration_ms": result.duration_ms,
                "output_truncated": result.output_truncated,
            },
        )
        return result
