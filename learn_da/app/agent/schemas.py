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

# 阶段 3：教学反馈五态（与服务端证据解析器对齐）
TeachingState = Literal[
    "execution_failed",
    "verification_failed",
    "passed_unconfirmed",
    "unverifiable",
    "no_evidence",
]

# 阶段 3：下一步动作（服务端权威决定，LLM 不得覆盖）
TeachingNextAction = Literal[
    "inspect_result",
    "retry_exercise",
    "confirm_lesson",
    "retry_later",
]

AgentFeedbackValue = Literal["helpful", "not_helpful"]


class AgentChatMessage(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1, max_length=4000)


class AgentContext(BaseModel):
    current_code: str | None = Field(
        default=None,
        alias="currentCode",
        max_length=12000,
    )
    # 阶段 3：以下三个字段仅供前端展示透传，不再作为教学判断的事实来源。
    # Agent 的练习证据由服务端 AgentEvidenceResolver 从数据库解析，
    # 客户端自报值不得影响执行/验证状态的判定。
    last_error: str | None = Field(
        default=None, alias="lastError", max_length=4000)
    current_lesson: str | None = Field(
        default=None,
        alias="currentLesson",
        max_length=200,
    )
    # 阶段 3：可选 attempt 定位线索，服务端校验归属后作为证据解析入口
    attempt_id: int | None = Field(
        default=None,
        alias="attemptId",
        ge=1,
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


class AgentFeedbackRequest(BaseModel):
    """用户对某次 Agent 交互的反馈（阶段 3 Task 3）。"""

    interaction_id: int = Field(alias="interactionId", ge=1)
    feedback: AgentFeedbackValue


class AgentFeedbackResponse(BaseResponseModel):
    recorded: bool = True
    interaction_id: int = Field(alias="interactionId")


class TeachingFeedback(BaseResponseModel):
    """结构化教学反馈契约（阶段 3 Task 2）。

    所有字段均由服务端决定，保证 UI 消费稳定 schema，不依赖从 Markdown
    文本猜测状态。state / attemptId / nextAction 由服务端证据解析器决定，
    LLM 不得覆盖。
    """

    state: TeachingState
    attempt_id: int | None = Field(default=None, alias="attemptId")
    evidence_summary: str = Field(alias="evidenceSummary")
    diagnosis: str
    hint_level: int = Field(default=1, alias="hintLevel", ge=1, le=3)
    next_action: TeachingNextAction = Field(alias="nextAction")


class AgentChatData(BaseResponseModel):
    content: str
    model: str
    used_fallback: bool = False
    # used_fallback=True 时的降级原因（LLMErrorReason），成功时为 None
    fallback_reason: str | None = None
    # 用于把前端反馈关联回本次审计交互。
    interaction_id: int | None = Field(default=None, alias="interactionId")
    # 阶段 3：结构化教学反馈。
    teaching_feedback: TeachingFeedback | None = Field(
        default=None, alias="teachingFeedback"
    )
