from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
    last_error: str | None = Field(default=None, alias="lastError", max_length=4000)
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
    history: list[AgentChatMessage] = Field(default_factory=list, max_length=6)
    context: AgentContext | None = None


class AgentChatData(BaseResponseModel):
    tool_name: ToolName
    content: str
    model: str
    used_fallback: bool = False
    route: "AgentRouteInfo | None" = None
    structured_result: "AgentStructuredResult | None" = None


class AgentRouteInfo(BaseResponseModel):
    tool_name: ToolName
    confidence: float
    reason: str
    strategy: str = "keyword"
    matched_keyword: str | None = None


class AgentResultSection(BaseResponseModel):
    title: str
    content: str


class AgentCodeBlock(BaseResponseModel):
    language: str | None = None
    code: str


class AgentStructuredResult(BaseResponseModel):
    kind: ToolName
    sections: list[AgentResultSection] = []
    code_blocks: list[AgentCodeBlock] = []


class FixCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12000)
    error_message: str = Field(alias="errorMessage", min_length=1, max_length=4000)
    context: AgentContext | None = None


class AgentRunVerification(BaseResponseModel):
    verified: bool
    status: str
    stdout: str = ""
    stderr: str = ""
    execution_time: int
    used_sandbox: str


class FixCodeResponse(BaseResponseModel):
    fixed_code: str
    explanation: str
    model: str
    used_fallback: bool = False
    verification: AgentRunVerification | None = None
    structured_result: AgentStructuredResult | None = None


class ExplainCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12000)
    context: AgentContext | None = None


class ExplainCodeResponse(BaseResponseModel):
    explanation: str
    model: str
    used_fallback: bool = False
    structured_result: AgentStructuredResult | None = None
