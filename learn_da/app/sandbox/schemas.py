from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AliasChoices, BaseModel, Field

from app.utils.base_response import BaseResponseModel


class SafetyCheckResult(BaseModel):
    is_safe: bool
    reason: str | None = None


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


ExecutionSource = Literal["playground", "agent_suggested"]


class RunnerExecutionRequest(BaseResponseModel):
    request_id: UUID
    code: str = Field(min_length=1, max_length=5000)
    language: Literal["python"] = "python"
    source: ExecutionSource = "playground"


class SandboxExecutionResult(BaseResponseModel):
    request_id: UUID = Field(default_factory=uuid4)
    execution_id: UUID = Field(default_factory=uuid4)
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    error_type: str | None = None
    duration_ms: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices(
            "duration_ms",
            "durationMs",
            "execution_time",
            "executionTime",
        ),
    )
    output_truncated: bool = False
    legacy_used_sandbox: str = Field(
        default="",
        validation_alias=AliasChoices("legacy_used_sandbox", "used_sandbox"),
        exclude=True,
        repr=False,
    )

    @property
    def execution_time(self) -> int:
        return self.duration_ms

    @property
    def used_sandbox(self) -> str:
        return self.legacy_used_sandbox
