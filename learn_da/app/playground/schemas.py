from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import AliasChoices, BaseModel, Field

from app.sandbox.schemas import ExecutionSource, ExecutionStatus
from app.utils.base_response import BaseResponseModel


class ExerciseVerification(BaseResponseModel):
    """练习验证结果"""

    status: str  # passed / failed / unverifiable
    failure_reason: str | None = None
    validator_type: str | None = None


class ExecuteCodeRequest(BaseResponseModel):
    request_id: UUID = Field(default_factory=uuid4)
    code: str = Field(min_length=1, max_length=5000)
    language: Literal["python", "sql"] = "python"
    source: ExecutionSource = "playground"
    session_id: str | None = None
    # Phase 2: 练习执行（可选）
    lesson_slug: str | None = None
    exercise_id: str | None = None


class FormatCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=5000)
    language: Literal["python"] = "python"


class FormatCodeResponse(BaseResponseModel):
    formatted: str
    changed: bool


class DataFrameResult(BaseResponseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = False


class ExecuteCodeResponse(BaseResponseModel):
    request_id: UUID = Field(default_factory=uuid4)
    execution_id: UUID | None = None
    source: ExecutionSource = "playground"
    status: ExecutionStatus
    stdout: str
    stderr: str
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
    result_type: Literal["text", "dataframe", "error"] = "text"
    dataframe: DataFrameResult | None = None
    # Phase 2: 练习执行结果
    attempt_id: int | None = None
    verification: ExerciseVerification | None = None
