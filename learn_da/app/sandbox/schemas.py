from pydantic import BaseModel


class SafetyCheckResult(BaseModel):
    is_safe: bool
    reason: str | None = None


class SandboxExecutionResult(BaseModel):
    status: str
    stdout: str = ""
    stderr: str = ""
    execution_time: int   # renamed from execution_time_ms, will serialize as executionTime
    used_sandbox: str
