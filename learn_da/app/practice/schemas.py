"""
Phase 2: 可验证练习闭环 - Pydantic Schemas
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.utils.base_response import BaseResponseModel


class VerificationResult(BaseResponseModel):
    """验证结果"""

    status: str  # passed / failed / unverifiable
    failure_reason: str | None = None
    validator_type: str | None = None


class ExerciseAttemptSummary(BaseResponseModel):
    """练习尝试摘要（Agent/推荐只读此摘要，不暴露完整代码）"""

    id: int
    attempt_id: int = Field(alias="id")
    exercise_id: str
    lesson_slug: str
    execution_status: str
    verification_status: str
    failure_reason: str | None = None
    created_time: str | None = None
    duration_ms: int | None = None

    class Config:
        populate_by_name = True


class ExerciseAttemptDetail(BaseResponseModel):
    """练习尝试详情（含代码，仅本 visitor 可读）"""

    id: int
    attempt_id: int = Field(alias="id")
    visitor_id: str
    request_id: str
    exercise_id: str
    lesson_slug: str
    language: str
    code: str
    source: str
    execution_status: str
    verification_status: str
    failure_reason: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration_ms: int | None = None
    created_time: str | None = None

    class Config:
        populate_by_name = True


class ExerciseResumeResponse(BaseResponseModel):
    """恢复练习响应"""

    exercise_id: str
    lesson_slug: str
    code: str  # 最近未通过尝试的代码，或 starter code
    language: str
    is_resumed: bool  # True=从最近尝试恢复，False=starter code
    last_attempt: ExerciseAttemptSummary | None = None
    exercise_title: str = ""
    objective: str = ""
    hints: list[str] = []
    starter_code: str = ""
