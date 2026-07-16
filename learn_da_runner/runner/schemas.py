"""Wire contract schemas — must match the API-side Task 1 contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        use_enum_values=True,
    )


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


ExecutionSource = Literal["playground", "agent_suggested"]


class RunnerExecutionRequest(_CamelModel):
    request_id: UUID
    code: str = Field(min_length=1, max_length=5000)
    language: Literal["python"] = "python"
    source: ExecutionSource = "playground"


class RunnerExecutionResult(_CamelModel):
    request_id: UUID
    execution_id: UUID
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    error_type: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    output_truncated: bool = False
