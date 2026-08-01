"""阶段 3 Task 1：服务端练习证据解析器。

每次 Agent chat 调用模型前，按服务端身份构造可信教学上下文。证据来源是
数据库中的 ``ExerciseAttempt`` 与 ``LearnerState`` 投影；客户端自报的
``stdout`` / ``stderr`` / ``lastError`` 不作为事实来源，避免伪造状态进入
教学判断。

设计约束（见计划）：
- ``visitor_id`` 只能由服务端匿名会话注入，模型和客户端均不能指定；
- Attempt / 执行状态 / 验证状态 / 错误类型 / 已完成课程必须从数据库读取；
- 自动注入给模型的是截断后的证据摘要，绝不自动注入历史 Attempt 的完整代码；
- 解析顺序：指定 Attempt -> 该课程最近 Attempt -> 无 Attempt；
- 禁止跨 visitor 查询，伪造 ``attemptId`` / lesson slug 得不到他人证据。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.utils.base_response import BaseResponseModel

if TYPE_CHECKING:
    from app.learner_state.service import LearnerStateService
    from app.practice.models import ExerciseAttempt
    from app.practice.repository import PracticeRepository

    from .schemas import TeachingFeedback
EvidenceState = Literal[
    "execution_failed",
    "verification_failed",
    "passed_unconfirmed",
    "unverifiable",
    "no_evidence",
]

# 执行状态归一化：写入路径用 ExecutionStatus 枚举值（success/error/timeout/
# rejected/unavailable）；部分历史测试用 "completed"，一并视为成功。
_SUCCESS_EXECUTION = frozenset({"success", "completed", "ok"})
_UNAVAILABLE_EXECUTION = frozenset({"unavailable"})

# 截断长度：注入给模型的 stdout/stderr 摘要上限，避免 prompt 膨胀。
MAX_STDOUT_SUMMARY = 500
MAX_STDERR_SUMMARY = 500


class AgentLearningEvidence(BaseResponseModel):
    """服务端解析出的可信教学证据。

    不包含历史 Attempt 的完整 ``code`` 字段；stdout/stderr 已截断。
    """

    state: EvidenceState
    lesson_slug: str | None = None
    exercise_id: str | None = None
    attempt_id: int | None = None
    execution_status: str | None = None
    verification_status: str | None = None
    failure_reason: str | None = None
    duration_ms: int | None = None
    stdout_summary: str | None = None
    stderr_summary: str | None = None
    lesson_completed: bool = False
    evidence_time: str | None = None


def derive_state(
    execution_status: str | None,
    verification_status: str | None,
) -> EvidenceState:
    """根据执行与验证状态推导五态之一。

    五态对应计划：execution_failed / verification_failed /
    passed_unconfirmed / unverifiable / no_evidence。
    """
    if execution_status is None and verification_status is None:
        return "no_evidence"

    if execution_status in _UNAVAILABLE_EXECUTION:
        return "unverifiable"
    if verification_status == "unverifiable":
        return "unverifiable"

    if execution_status not in _SUCCESS_EXECUTION:
        # error / timeout / rejected / 未知失败值
        return "execution_failed"

    # 执行成功后看验证结果
    if verification_status == "failed":
        return "verification_failed"
    if verification_status == "passed":
        return "passed_unconfirmed"
    # not_run：执行成功但未跑断言，无法判定目标是否达成 -> 不可验证
    return "unverifiable"


def _truncate(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "…(截断)"


class AgentEvidenceResolver:
    """按服务端身份解析当前学习者最近一次可信练习证据。

    依赖注入而非全局状态，便于在 AgentService 中复用现有服务实例，
    也便于单测用 mock 替换。
    """

    def __init__(
        self,
        practice_repo: "PracticeRepository",
        learner_state_service: "LearnerStateService | None" = None,
    ) -> None:
        self.practice_repo = practice_repo
        self.learner_state_service = learner_state_service

    async def resolve(
        self,
        visitor_id: str,
        lesson_slug: str | None = None,
        attempt_id: int | None = None,
    ) -> AgentLearningEvidence:
        """依次解析：指定 Attempt -> 该课程最近 Attempt -> 无 Attempt。"""
        attempt: ExerciseAttempt | None = None

        # 1) 优先按客户端提供的 attemptId 定位（服务端校验归属）
        if attempt_id is not None:
            attempt = await self.practice_repo.get_by_id(attempt_id, visitor_id)
            # 校验 attempt 与客户端声明的 lesson 一致；不一致则不采信该 attempt
            if attempt is not None and lesson_slug and attempt.lesson_slug != lesson_slug:
                lesson_completed = await self._read_lesson_completed(
                    visitor_id, lesson_slug
                )
                return AgentLearningEvidence(
                    state="no_evidence",
                    lesson_slug=attempt.lesson_slug,
                    lesson_completed=lesson_completed,
                )

        # 2) 回退到该课程最近一次 Attempt
        if attempt is None and lesson_slug:
            attempt = await self.practice_repo.get_latest_by_lesson(
                visitor_id, lesson_slug
            )

        # 3) 解析课程完成状态（单独查询，不依赖客户端）
        lesson_completed = await self._read_lesson_completed(visitor_id, lesson_slug)

        if attempt is None:
            return AgentLearningEvidence(
                state="no_evidence",
                lesson_completed=lesson_completed,
            )

        return self._build_evidence(attempt, lesson_completed)

    async def _read_lesson_completed(
        self, visitor_id: str, lesson_slug: str | None
    ) -> bool:
        if not lesson_slug or self.learner_state_service is None:
            return False
        try:
            progress = await self.learner_state_service.get_lesson_progress(
                visitor_id, lesson_slug
            )
        except Exception:
            # 读取完成状态失败不应阻断 Agent 回答；按未完成处理
            return False
        return progress is not None and progress.status == "completed"

    @staticmethod
    def _build_evidence(
        attempt: "ExerciseAttempt",
        lesson_completed: bool,
    ) -> AgentLearningEvidence:
        state = derive_state(attempt.execution_status, attempt.verification_status)
        evidence_time = (
            attempt.created_time.strftime("%Y-%m-%d %H:%M:%S")
            if attempt.created_time
            else None
        )
        return AgentLearningEvidence(
            state=state,
            lesson_slug=attempt.lesson_slug,
            exercise_id=attempt.exercise_id,
            attempt_id=attempt.id,
            execution_status=attempt.execution_status,
            verification_status=attempt.verification_status,
            failure_reason=attempt.failure_reason,
            duration_ms=attempt.duration_ms,
            stdout_summary=_truncate(attempt.stdout, MAX_STDOUT_SUMMARY),
            stderr_summary=_truncate(attempt.stderr, MAX_STDERR_SUMMARY),
            lesson_completed=lesson_completed,
            evidence_time=evidence_time,
        )


# =====================================================
# 阶段 3 Task 2：结构化教学反馈构造
# =====================================================

_STATE_SUMMARY: dict[EvidenceState, str] = {
    "execution_failed": "代码执行失败，需要先修复错误",
    "verification_failed": "代码执行成功，但练习断言未通过",
    "passed_unconfirmed": "练习已通过，可以确认课程完成",
    "unverifiable": "结果不可验证，Runner 不可用或未运行断言",
    "no_evidence": "暂无可用练习证据",
}

_STATE_DIAGNOSIS: dict[EvidenceState, str] = {
    "execution_failed": "当前代码存在执行错误，优先定位语法或运行时问题",
    "verification_failed": "代码能运行，但输出与练习目标不一致",
    "passed_unconfirmed": "练习目标已达成",
    "unverifiable": "无法确认练习是否通过，建议稍后重试",
    "no_evidence": "尚未产生可验证的练习证据",
}


def derive_next_action(evidence: AgentLearningEvidence) -> str:
    """根据证据状态与课程完成情况推导下一步动作（服务端权威）。"""
    if evidence.state == "execution_failed":
        return "retry_exercise"
    if evidence.state == "verification_failed":
        return "retry_exercise"
    if evidence.state == "passed_unconfirmed":
        return "confirm_lesson" if not evidence.lesson_completed else "inspect_result"
    if evidence.state == "unverifiable":
        return "retry_later"
    # no_evidence
    return "inspect_result"


def build_teaching_feedback(
    evidence: AgentLearningEvidence,
    hint_level: int = 1,
) -> "TeachingFeedback":
    """由服务端证据构造结构化教学反馈。

    state / attemptId / nextAction / evidenceSummary / diagnosis 均由服务端
    决定；hint_level 由调用方根据连续求助次数传入。LLM 只负责生成 content
    正文（与 hint_level 对应的教学文案），不得覆盖本结构。
    """
    from .schemas import TeachingFeedback

    return TeachingFeedback(
        state=evidence.state,
        attempt_id=evidence.attempt_id,
        evidence_summary=_STATE_SUMMARY.get(evidence.state, str(evidence.state)),
        diagnosis=_STATE_DIAGNOSIS.get(evidence.state, str(evidence.state)),
        hint_level=max(1, min(3, hint_level)),
        next_action=derive_next_action(evidence),  # type: ignore[arg-type]
    )
