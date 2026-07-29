from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.learning.schemas import LearningRecommendation
from app.sandbox.schemas import ExecutionStatus
from app.utils.base_response import BaseResponseModel


MessageRole = Literal["user", "assistant", "system"]
ToolName = Literal[
    "generate_example_code",
    "generate_exercise",
    "fix_code",
    "explain_code",
    "suggest_next_step",
    "general_chat",
]


class AgentChatMessage(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1, max_length=4000)


class AgentContext(BaseModel):
    current_code: str | None = Field(
        default=None,
        alias="currentCode",
        max_length=12000,
    )
    last_error: str | None = Field(
        default=None, alias="lastError", max_length=4000)
    current_lesson: str | None = Field(
        default=None,
        alias="currentLesson",
        max_length=200,
    )
    lesson_title: str | None = Field(
        default=None,
        alias="lessonTitle",
        max_length=300,
    )
    lesson_category: str | None = Field(
        default=None,
        alias="lessonCategory",
        max_length=100,
    )
    lesson_content: str | None = Field(
        default=None,
        alias="lessonContent",
        max_length=8000,
    )
    stdout: str | None = Field(default=None, max_length=4000)
    stderr: str | None = Field(default=None, max_length=4000)


class AgentChatPayload(BaseModel):
    message: str | None = Field(default=None, min_length=1, max_length=4000)


class AgentChatRequest(BaseModel):
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    payload: AgentChatPayload | None = None
    history: list[AgentChatMessage] = Field(
        default_factory=list, max_length=20)
    context: AgentContext | None = None


class AgentChatData(BaseResponseModel):
    content: str
    model: str
    used_fallback: bool = False
    # used_fallback=True 时的降级原因（LLMErrorReason），成功时为 None
    fallback_reason: str | None = None