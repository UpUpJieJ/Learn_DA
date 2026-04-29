import time

from fastapi import status

from app.core.exceptions.base_exceptions import BusinessException
from config.settings import settings

from .docker_runner import DockerSandboxRunner
from .local_runner import LocalSubprocessRunner
from .safety_check import validate_code
from .schemas import SandboxExecutionResult


class SandboxService:
    def __init__(self, runner=None):
        self.runner = runner

    def _get_runner(self):
        if self.runner is not None:
            return self.runner
        if settings.SANDBOX_DOCKER_ENABLED:
            return DockerSandboxRunner()
        if settings.SANDBOX_LOCAL_ENABLED:
            return LocalSubprocessRunner()
        return None

    def execute(self, code: str) -> SandboxExecutionResult:
        safety_result = validate_code(code)
        if not safety_result.is_safe:
            raise BusinessException(
                message=safety_result.reason or "代码未通过安全校验",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        runner = self._get_runner()
        if runner is not None:
            return runner.execute(code, timeout=settings.SANDBOX_TIMEOUT_SECONDS)

        # Fallback mock mode
        started_at = time.perf_counter()
        preview = code.strip().splitlines()[:6]
        return SandboxExecutionResult(
            status="mocked",
            stdout="Mock sandbox result\n" + "\n".join(preview),
            stderr="",
            execution_time=int((time.perf_counter() - started_at) * 1000),
            used_sandbox="mock",
        )
