from typing import Any, Literal

from pydantic import BaseModel, Field

from app.utils.base_response import BaseResponseModel


class ExecuteCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=5000)
    language: Literal["python", "sql"] = "python"
    session_id: str | None = None


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
    status: str
    stdout: str
    stderr: str
    execution_time: int   # serializes as executionTime via alias_generator
    used_sandbox: str     # serializes as usedSandbox
    result_type: Literal["text", "dataframe", "error"] = "text"
    dataframe: DataFrameResult | None = None
