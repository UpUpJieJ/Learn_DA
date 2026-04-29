import subprocess
import sys
import time

from .schemas import SandboxExecutionResult


class LocalSubprocessRunner:
    """在本地子进程中执行 Python 代码（开发/测试环境）"""

    def execute(self, code: str, timeout: int = 10) -> SandboxExecutionResult:
        started_at = time.perf_counter()
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            execution_time = int((time.perf_counter() - started_at) * 1000)
            status = "success" if result.returncode == 0 else "error"
            return SandboxExecutionResult(
                status=status,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                used_sandbox="local",
            )
        except subprocess.TimeoutExpired:
            execution_time = int((time.perf_counter() - started_at) * 1000)
            return SandboxExecutionResult(
                status="timeout",
                stdout="",
                stderr="执行超时，请检查是否存在死循环或耗时操作",
                execution_time=execution_time,
                used_sandbox="local",
            )
        except Exception as exc:
            execution_time = int((time.perf_counter() - started_at) * 1000)
            return SandboxExecutionResult(
                status="error",
                stdout="",
                stderr=str(exc),
                execution_time=execution_time,
                used_sandbox="local",
            )
