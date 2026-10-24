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
# 改版 M4 起新增 next_task：工作区的课程完成度由任务通过数推导，任务通过后用
# 「继续下一个任务」替代旧的「确认完成本课」。
TeachingNextAction = Literal[
    "inspect_result",
    "retry_exercise",
    "confirm_lesson",
    "retry_later",
    "next_task",
]

AgentFeedbackValue = Literal["helpful", "not_helpful"]


class AgentChatMessage(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1, max_length=4000)


class AgentRecentRun(BaseModel):
    """工作区里最近一次单元格执行的自报摘要（仅供排错参考，不是教学证据）。

    任务判定与断言结果一律以服务端 ``task_attempts`` 为准；这里只用于让模型
    知道「用户刚才在哪个格子撞了什么错」，例如草稿格里的 NameError —— 这类
    执行不会产生 TaskAttempt，服务端证据里看不到。
    """

    cell_id: str | None = Field(default=None, alias="cellId", max_length=64)
    status: str | None = Field(default=None, max_length=32)
    error_type: str | None = Field(default=None, alias="errorType", max_length=120)
    stderr_first_line: str | None = Field(
        default=None, alias="stderrFirstLine", max_length=400
    )
    assertions_failed: list[str] = Field(
        default_factory=list, alias="assertionsFailed", max_length=8
    )


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
    # 改版 M4：当前聚焦的任务 id（工作区右栏使用）。仅作证据定位线索，
    # 提交状态仍由服务端从 task_attempts 读取。
    current_task: str | None = Field(
        default=None,
        alias="currentTask",
        max_length=64,
    )
    # 改版 E1：工作区定位线索。sessionId 用于日志与后续 HintUsage 关联，
    # cellId 指向当前聚焦的格子，recentRuns 是最近的执行摘要（见上）。
    session_id: int | None = Field(
        default=None, alias="sessionId", ge=1
    )
    cell_id: str | None = Field(
        default=None, alias="cellId", max_length=64
    )
    recent_runs: list[AgentRecentRun] = Field(
        default_factory=list, alias="recentRuns", max_length=3
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
