"""学习工作区 API 契约（改版 M1）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

CellKind = Literal["starter", "task", "scratch"]
CellStatus = Literal["stale", "ok", "failed", "skipped"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateSessionRequest(_CamelModel):
    lesson_slug: str = Field(min_length=1, max_length=64)


class UpdateCellRequest(_CamelModel):
    code: str = Field(default="", max_length=20000)


class RunCellRequest(_CamelModel):
    request_id: str = Field(min_length=1, max_length=64)


class SubmitTaskRequest(_CamelModel):
    request_id: str = Field(min_length=1, max_length=64)


class CellPayload(_CamelModel):
    cell_id: str
    position: int
    kind: CellKind = "task"
    task_id: str | None = None
    language: str = "python"
    code: str = ""
    status: CellStatus = "stale"
    has_assertions: bool = False


class TaskPayload(_CamelModel):
    task_id: str
    title: str
    cell_id: str
    objective: str = ""
    status: Literal["todo", "passed", "failed", "skipped"] = "todo"


class AssertionResult(_CamelModel):
    id: str
    type: str | None = None
    title: str = ""
    status: Literal["passed", "failed", "error", "timeout", "skipped"]
    actual: str | None = None
    detail: str | None = None
    duration_ms: int = 0


class CellRunResult(_CamelModel):
    cell_id: str
    status: str
    stdout: str = ""
    stderr: str = ""
    error_type: str | None = None
    duration_ms: int = 0
    truncated: bool = False


class RunResponse(_CamelModel):
    request_id: str
    session_id: int
    cell_id: str
    verdict: Literal["execution_failed", "assertion_failed", "passed"]
    cells: list[CellRunResult] = Field(default_factory=list)
    assertions: list[AssertionResult] = Field(default_factory=list)
    assertions_skipped: bool = False
    task_status: Literal["passed", "failed", "skipped"] | None = None
    duration_ms: int = 0
    error: str = ""


class SessionSnapshot(_CamelModel):
    session_id: int
    lesson_slug: str
    content_version: str
    cells: list[CellPayload] = Field(default_factory=list)
    tasks: list[TaskPayload] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    stale_from: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)