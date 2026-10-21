"""Wire contract schemas — must match the API-side Task 1 contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
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


# ---------------------------------------------------------------------------
# Session execution (replay-style whole-workspace run)
# ---------------------------------------------------------------------------


class SessionCell(_CamelModel):
    cell_id: str = Field(min_length=1, max_length=64)
    code: str = Field(default="", max_length=20000)
    language: Literal["python", "sql"] = "python"


class RunnerSessionRequest(_CamelModel):
    """Everything needed to replay a cell list from scratch.

    ``datasets`` maps a relative path (``ecommerce/orders.csv``) to base64
    bytes; ``refs`` maps assertion reference names to base64 parquet/JSON;
    ``runtime`` is the assertion runtime source supplied by the backend, so the
    sandbox image never has to be rebuilt when the DSL changes.
    """

    request_id: UUID
    cells: list[SessionCell] = Field(min_length=1, max_length=40)
    stop_at: str | None = None
    datasets: dict[str, str] = Field(default_factory=dict)
    runtime: str | None = Field(default=None, max_length=200_000)
    refs: dict[str, str] = Field(default_factory=dict)
    assertions: list[dict[str, Any]] = Field(default_factory=list)


class RunnerSessionResult(_CamelModel):
    request_id: UUID
    execution_id: UUID
    status: ExecutionStatus
    verdict: Literal[
        "execution_failed", "assertion_failed", "passed"
    ] = "execution_failed"
    cells: list[dict[str, Any]] = Field(default_factory=list)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    assertions_skipped: bool = True
    executed_upto: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    error_type: str | None = None
    error: str = ""
