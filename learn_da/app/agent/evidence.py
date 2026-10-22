"""服务端教学证据解析器（阶段 3 建立，改版 M4 起改读工作区记录）。

每次 Agent chat 调用模型前，按服务端身份构造可信教学上下文。证据来源是数据库：

* 改版后：``task_attempts``（任务提交，含 Runner verdict 与每条断言的
  ``actual``）+ 内容侧任务总数。这是唯一还在写入的证据表。
* 改版前：``exercise_attempts``（旧练习链路，已冻结只读），仅当课程没有
  ``workspace`` 定义时才会走到。

客户端自报的 ``stdout`` / ``stderr`` / ``lastError`` 不作为事实来源，避免伪造
状态进入教学判断。

设计约束：
- ``visitor_id`` 只能由服务端匿名会话注入，模型和客户端均不能指定；
- 提交状态 / verdict / 断言结果 / 已完成任务数必须从数据库读取；
- 注入给模型的是截断后的证据摘要，绝不自动注入历史提交的完整代码；
- 解析顺序：指定 attempt -> 当前任务最近提交 -> 该课程最近提交 -> 无提交；
- 禁止跨 visitor 查询，伪造 ``attemptId`` / lesson slug 得不到他人证据。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from app.utils.base_response import BaseResponseModel

if TYPE_CHECKING:
    from app.learner_state.service import LearnerStateService
    from app.practice.models import ExerciseAttempt
    from app.practice.repository import PracticeRepository
    from app.workspace.models import TaskAttempt
    from app.workspace.repository import WorkspaceReadRepository

    from .schemas import TeachingFeedback

EvidenceState = Literal[
    "execution_failed",
    "verification_failed",
    "passed_unconfirmed",
    "unverifiable",
    "no_evidence",
]
EvidenceSource = Literal["workspace", "exercise"]

# 执行状态归一化：写入路径用 ExecutionStatus 枚举值（success/error/timeout/
# rejected/unavailable）；部分历史测试用 "completed"，一并视为成功。
_SUCCESS_EXECUTION = frozenset({"success", "completed", "ok"})
_UNAVAILABLE_EXECUTION = frozenset({"unavailable"})

# 截断长度：注入给模型的摘要上限，避免 prompt 膨胀。
MAX_STDOUT_SUMMARY = 500
MAX_STDERR_SUMMARY = 500
MAX_DETAIL_SUMMARY = 300
MAX_ASSERTIONS_IN_EVIDENCE = 8


class AgentAssertionEvidence(BaseResponseModel):
    """单条断言的服务端结果（失败时带实际值，供模型定位问题）。"""

    assertion_id: str | None = None
    title: str | None = None
    status: str | None = None
    detail: str | None = None
    actual: str | None = None


class AgentLearningEvidence(BaseResponseModel):
    """服务端解析出的可信教学证据。

    不包含历史提交的完整 ``code`` 字段；stdout/stderr/断言实际值均已截断。
    """

    state: EvidenceState
    source: EvidenceSource | None = None
    lesson_slug: str | None = None
    # 旧练习链路字段
    exercise_id: str | None = None
    execution_status: str | None = None
    verification_status: str | None = None
    failure_reason: str | None = None
    stdout_summary: str | None = None
    stderr_summary: str | None = None
    # 工作区链路字段
    attempt_id: int | None = None
    attempt_no: int | None = None
    task_id: str | None = None
    task_title: str | None = None
    task_objective: str | None = None
    verdict: str | None = None
    assertions: list[AgentAssertionEvidence] = Field(default_factory=list)
    tasks_passed: int | None = None
    tasks_total: int | None = None
    current_task_id: str | None = None
    duration_ms: int | None = None
    lesson_completed: bool = False
    evidence_time: str | None = None
    # 客户端编辑器里的代码是否就是这次的提交代码。False 表示用户改过但没提交，
    # 此时 prompt 必须提醒模型"编辑器代码可能未保存/未提交"，避免它拿旧代码
    # 解释任务状态（曾出现「已通过」的同时说"你还缺 X 列"的自相矛盾回答）。
    code_matches_editor: bool | None = None


def derive_state(
    execution_status: str | None,
    verification_status: str | None,
) -> EvidenceState:
    """旧练习链路的五态推导（保留给冻结的 exercise_attempts 数据）。

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


def derive_workspace_state(
    verdict: str | None,
    status: str | None,
) -> EvidenceState:
    """工作区链路：由 Runner verdict（回退到教学状态）推导五态。"""
    if verdict == "passed" or status == "passed":
        return "passed_unconfirmed"
    if verdict == "execution_failed":
        return "execution_failed"
    if verdict == "assertion_failed":
        return "verification_failed"
    if status == "skipped":
        # 断言未求值（前面单元格没跑通），无法判定任务是否达成
        return "unverifiable"
    if status == "failed":
        # 历史行没有 verdict：只能确定"执行成功但没通过断言"这一层
        return "verification_failed"
    return "no_evidence"


def _truncate(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "…(截断)"


def _parse_assertions(raw: str | None) -> list[AgentAssertionEvidence]:
    """把 TaskAttempt.assertions 的 JSON 还原成证据条目（失败优先、有上限）。"""
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    parsed: list[AgentAssertionEvidence] = [
        AgentAssertionEvidence(
            assertion_id=str(item.get("id") or "") or None,
            title=_truncate(str(item.get("title") or "") or None, 120),
            status=str(item.get("status") or "") or None,
            detail=_truncate(str(item.get("detail") or "") or None, MAX_DETAIL_SUMMARY),
            actual=_truncate(str(item.get("actual") or "") or None, MAX_DETAIL_SUMMARY),
        )
        for item in items
        if isinstance(item, dict)
    ]
    # 失败/错误/超时的断言是定位问题的关键，排在前面
    parsed.sort(key=lambda item: 0 if item.status not in {"passed", None} else 1)
    return parsed[:MAX_ASSERTIONS_IN_EVIDENCE]


class AgentEvidenceResolver:
    """按服务端身份解析当前学习者最近一次可信任务提交。

    优先读工作区记录；课程没有 ``workspace`` 定义时退回冻结的练习记录。
    """

    def __init__(
        self,
        practice_repo: "PracticeRepository | None" = None,
        learner_state_service: "LearnerStateService | None" = None,
        workspace_repo: "WorkspaceReadRepository | None" = None,
    ) -> None:
        self.practice_repo = practice_repo
        self.learner_state_service = learner_state_service
        self.workspace_repo = workspace_repo

    async def resolve(
        self,
        visitor_id: str,
        lesson_slug: str | None = None,
        attempt_id: int | None = None,
        task_id: str | None = None,
        editor_code: str | None = None,
    ) -> AgentLearningEvidence:
        """依次解析：指定 attempt -> 当前任务最近提交 -> 该课最近提交 -> 无提交。

        ``editor_code`` 只用来判断「编辑器里的代码是否就是这次提交的代码」，
        不会出现在证据里，也不会落库。
        """
        if self.workspace_repo is not None and lesson_slug:
            from app.workspace.repository import spec_for

            spec = spec_for(lesson_slug)
            if spec is not None:
                return await self._resolve_workspace(
                    visitor_id=visitor_id,
                    lesson_slug=lesson_slug,
                    task_id=task_id or self._guess_task(lesson_slug),
                    attempt_id=attempt_id,
                    spec=spec,
                    editor_code=editor_code,
                )
        return await self._resolve_exercise(
            visitor_id=visitor_id,
            lesson_slug=lesson_slug,
            attempt_id=attempt_id,
        )

    @staticmethod
    def _guess_task(lesson_slug: str) -> str | None:
        """没有明确 task_id 时，取内容里第一个任务作为默认关注点。"""
        from app.workspace.repository import spec_for

        spec = spec_for(lesson_slug)
        if spec is None or not spec.tasks:
            return None
        return spec.tasks[0].task_id

    async def _resolve_workspace(
        self,
        visitor_id: str,
        lesson_slug: str,
        task_id: str | None,
        attempt_id: int | None,
        spec,
        editor_code: str | None = None,
    ) -> AgentLearningEvidence:
        repo = self.workspace_repo
        assert repo is not None

        attempt: TaskAttempt | None = None
        if attempt_id is not None:
            candidate = await repo.get_attempt(visitor_id, attempt_id)
            # 归属校验：对方课程的 attempt 不采信
            if candidate is not None and candidate.lesson_slug == lesson_slug:
                attempt = candidate
                task_id = candidate.task_id
        if attempt is None:
            attempt = await repo.latest_attempt(
                visitor_id, lesson_slug, task_id=task_id
            )

        passed_ids, total = await repo.lesson_task_stats(visitor_id, lesson_slug)
        known_tasks = [task.task_id for task in spec.tasks]
        current_task = next(
            (item for item in known_tasks if item not in passed_ids), None
        )
        lesson_completed = bool(total) and len(passed_ids) >= total
        if attempt is None:
            return AgentLearningEvidence(
                state="no_evidence",
                source="workspace",
                lesson_slug=lesson_slug,
                task_id=task_id,
                tasks_passed=len(passed_ids),
                tasks_total=total,
                current_task_id=current_task,
                lesson_completed=lesson_completed,
            )

        task = spec.task(attempt.task_id)
        matches: bool | None = None
        if editor_code is not None:
            matches = (attempt.code or "").strip() == editor_code.strip()
        return AgentLearningEvidence(
            state=derive_workspace_state(attempt.verdict, attempt.status),
            source="workspace",
            lesson_slug=attempt.lesson_slug,
            attempt_id=attempt.id,
            attempt_no=attempt.attempt_no,
            task_id=attempt.task_id,
            task_title=_truncate(task.title if task else None, 200),
            task_objective=_truncate(task.objective if task else None, 400),
            verdict=attempt.verdict,
            assertions=_parse_assertions(attempt.assertions),
            tasks_passed=len(passed_ids),
            tasks_total=total,
            current_task_id=current_task,
            duration_ms=None,
            lesson_completed=lesson_completed,
            code_matches_editor=matches,
            evidence_time=(
                attempt.created_time.strftime("%Y-%m-%d %H:%M:%S")
                if attempt.created_time
                else None
            ),
        )

    async def _resolve_exercise(
        self,
        visitor_id: str,
        lesson_slug: str | None,
        attempt_id: int | None,
    ) -> AgentLearningEvidence:
        """旧练习链路（``exercise_attempts`` 已冻结，只为读历史数据保留）。"""
        if self.practice_repo is None:
            return AgentLearningEvidence(state="no_evidence")

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
                    source="exercise",
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
                source="exercise",
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
            source="exercise",
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
# 结构化教学反馈构造
# =====================================================

_STATE_SUMMARY: dict[EvidenceState, str] = {
    "execution_failed": "代码执行失败，需要先修复错误",
    "verification_failed": "代码执行成功，但断言未通过",
    "passed_unconfirmed": "任务已通过",
    "unverifiable": "结果不可验证，Runner 不可用或断言未求值",
    "no_evidence": "暂无可用任务证据",
}

_STATE_DIAGNOSIS: dict[EvidenceState, str] = {
    "execution_failed": "当前代码存在执行错误，优先定位语法或运行时问题",
    "verification_failed": "代码能运行，但结果与任务目标不一致",
    "passed_unconfirmed": "任务目标已达成",
    "unverifiable": "无法确认任务是否通过，建议稍后重试",
    "no_evidence": "尚未产生可验证的任务证据",
}


def derive_next_action(evidence: AgentLearningEvidence) -> str:
    """根据证据状态与任务完成度推导下一步动作（服务端权威）。"""
    if evidence.state in {"execution_failed", "verification_failed"}:
        return "retry_exercise"
    if evidence.state == "passed_unconfirmed":
        return "inspect_result" if evidence.lesson_completed else "next_task"
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