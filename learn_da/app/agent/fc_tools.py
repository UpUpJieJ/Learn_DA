"""受限 Function Calling 工具集（阶段 ④ Task 4.1）。

红线（见计划设计决策表）：
- 只提供四个只读工具，不存在任何执行/写入类工具；
- visitor_id 由服务端注入，不作为模型可控参数；
- get_recommendation 只读规则引擎结果，模型不得改排序。

改版 M4 起工具读的是工作区 ``task_attempts``（任务提交 + 断言实际值），
不再是冻结的 ``exercise_attempts``；``get_exercise_summary`` 随之更名为
``get_task_summary``，参数从 exerciseId 变成 taskId。

执行器对模型输入零信任：未知工具名、非法 JSON、参数校验失败都以错误
tool 消息回传（不抛异常），由编排循环决定给模型的重试机会。
"""

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, ValidationError

from app.utils import log

if TYPE_CHECKING:
    from app.learner_state.service import LearnerStateService
    from app.learning.recommendation import RecommendationService
    from app.workspace.repository import WorkspaceReadRepository

    from .knowledge import KnowledgeRetriever

# OpenAI tools JSON schema：描述面向模型，需说明何时该用哪个工具
FC_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "检索课程知识库。当用户问题涉及课程概念、语法用法、"
                "代码示例或报错含义时调用，返回最相关的课程片段。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词或问题描述，用用户的原话核心内容",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_learner_progress",
            "description": (
                "查询当前学习者的学习进度（已完成课程与最近访问课程）。"
                "当回答需要了解用户学到哪里时调用。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendation",
            "description": (
                "获取规则引擎给出的下一步学习建议。当用户询问接下来学什么、"
                "求推荐课程或学习路径时调用；结果排序不可更改。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_summary",
            "description": (
                "获取当前学习者的任务提交摘要：任务 id、判定结论（通过 / 断言未通过 / "
                "执行失败）、失败断言的说明与实际值。当用户询问「我这次为什么没过」"
                "「哪条断言错了」「我提交了几次」时调用。只返回摘要，不返回完整代码。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lesson_slug": {
                        "type": "string",
                        "description": "课程 slug，可选，不填则用当前课程",
                    },
                    "task_id": {
                        "type": "string",
                        "description": "任务 id（如 t1），可选，不填则返回该课最近提交",
                    },
                },
            },
        },
    },
]


class SearchKnowledgeParams(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class GetTaskSummaryParams(BaseModel):
    model_config = {"extra": "ignore"}
    lesson_slug: str | None = None
    task_id: str | None = None


class EmptyParams(BaseModel):
    model_config = {"extra": "ignore"}


_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "search_knowledge": SearchKnowledgeParams,
    "get_learner_progress": EmptyParams,
    "get_recommendation": EmptyParams,
    "get_task_summary": GetTaskSummaryParams,
}

# 每次工具调用最多回传的断言条数与文本上限：够定位问题，又不撑爆上下文
MAX_TOOL_ASSERTIONS = 5
MAX_TOOL_ASSERTION_TEXT = 240


@dataclass(frozen=True)
class ToolExecution:
    """单次工具执行结果；output 恒为可回传给模型的字符串。"""

    ok: bool
    output: str
    invalid_params: bool = False


class FCToolExecutor:
    """只读工具执行器：复用现有服务，所有失败都转成错误 tool 消息。"""

    def __init__(
        self,
        knowledge_retriever: "KnowledgeRetriever",
        visitor_id: str,
        learner_state_service: "LearnerStateService | None" = None,
        recommendation_service: "RecommendationService | None" = None,
        workspace_repo: "WorkspaceReadRepository | None" = None,
        current_lesson: str | None = None,
    ) -> None:
        self.knowledge_retriever = knowledge_retriever
        self.visitor_id = visitor_id
        self.learner_state_service = learner_state_service
        self.recommendation_service = recommendation_service
        self.workspace_repo = workspace_repo
        self.current_lesson = current_lesson
        # 编排循环用：本次会话内已成功执行过的工具名（意图标签来源）
        self.called_tools: list[str] = []

    async def execute(self, name: str, arguments: str) -> ToolExecution:
        started = time.monotonic()
        execution = await self._execute(name, arguments)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log.info(
            "[agent] fc_tool name={} ok={} invalid_params={} elapsed_ms={} args={}",
            name,
            execution.ok,
            execution.invalid_params,
            elapsed_ms,
            arguments[:200],
        )
        if execution.ok:
            self.called_tools.append(name)
        return execution

    async def _execute(self, name: str, arguments: str) -> ToolExecution:
        param_model = _PARAM_MODELS.get(name)
        if param_model is None:
            return ToolExecution(
                ok=False,
                output=json.dumps(
                    {"error": "unknown_tool", "message": f"工具 {name} 不存在"},
                    ensure_ascii=False,
                ),
            )
        try:
            raw = json.loads(arguments) if arguments.strip() else {}
            params = param_model.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            return ToolExecution(
                ok=False,
                output=json.dumps(
                    {"error": "invalid_params", "message": str(exc)[:300]},
                    ensure_ascii=False,
                ),
                invalid_params=True,
            )
        try:
            if name == "search_knowledge":
                return await self._search_knowledge(params)
            if name == "get_learner_progress":
                return await self._get_learner_progress()
            if name == "get_task_summary":
                return await self._get_task_summary(params)
            return await self._get_recommendation()
        except Exception as exc:  # 工具内部故障也不能中断编排循环
            return ToolExecution(
                ok=False,
                output=json.dumps(
                    {"error": "tool_failed", "message": str(exc)[:300]},
                    ensure_ascii=False,
                ),
            )

    async def _search_knowledge(
        self, params: SearchKnowledgeParams
    ) -> ToolExecution:
        chunks = await self.knowledge_retriever.search(
            query=params.query,
            current_lesson=self.current_lesson,
            limit=3,
        )
        payload = {
            "results": [
                {
                    "lesson_slug": chunk.lesson_slug,
                    "lesson_title": chunk.lesson_title,
                    "heading": chunk.heading,
                    "text": chunk.text[:900],
                }
                for chunk in chunks
            ]
        }
        return ToolExecution(ok=True, output=json.dumps(payload, ensure_ascii=False))

    async def _get_learner_progress(self) -> ToolExecution:
        payload: dict[str, Any] = {}
        if self.learner_state_service is not None:
            completed = await self.learner_state_service.get_completed_lessons(
                self.visitor_id
            )
            last_visited = await self.learner_state_service.get_last_visited(
                self.visitor_id
            )
            payload["completed_lessons"] = completed
            payload["last_visited"] = last_visited
        if self.workspace_repo is not None:
            try:
                progress = await self.workspace_repo.progress(self.visitor_id)
            except Exception as exc:  # 进度聚合失败不该让整轮对话失败
                payload["tasks_error"] = str(exc)[:200]
            else:
                payload["summary"] = progress.get("summary")
                payload["lessons"] = [
                    {
                        "lesson_slug": item.get("lessonSlug"),
                        "title": item.get("title"),
                        "status": item.get("status"),
                        "passed_tasks": item.get("passedTasks"),
                        "total_tasks": item.get("totalTasks"),
                        "current_task": item.get("currentTaskId"),
                    }
                    for item in progress.get("lessons") or []
                    if item.get("attempts")
                ]
        if not payload:
            return ToolExecution(
                ok=False,
                output=json.dumps(
                    {"error": "unavailable", "message": "学习进度服务不可用"},
                    ensure_ascii=False,
                ),
            )
        return ToolExecution(ok=True, output=json.dumps(payload, ensure_ascii=False))

    async def _get_recommendation(self) -> ToolExecution:
        if self.recommendation_service is None:
            return ToolExecution(
                ok=False,
                output=json.dumps(
                    {"error": "unavailable", "message": "推荐服务不可用"},
                    ensure_ascii=False,
                ),
            )
        response = await self.recommendation_service.get_recommendation(
            visitor_id=self.visitor_id,
            current_lesson_slug=self.current_lesson,
        )
        primary = getattr(response, "primary", None)
        payload = {
            "recommendation": primary.model_dump(mode="json") if primary else None
        }
        return ToolExecution(ok=True, output=json.dumps(payload, ensure_ascii=False))

    async def _get_task_summary(
        self, params: GetTaskSummaryParams
    ) -> ToolExecution:
        """获取任务提交摘要（只读，不暴露完整代码）。"""
        if self.workspace_repo is None:
            return ToolExecution(
                ok=False,
                output=json.dumps(
                    {"error": "unavailable", "message": "任务提交服务不可用"},
                    ensure_ascii=False,
                ),
            )
        lesson_slug = params.lesson_slug or self.current_lesson
        attempts = await self.workspace_repo.recent_attempts(
            self.visitor_id, lesson_slug=lesson_slug, limit=10
        )
        if params.task_id:
            attempts = [item for item in attempts if item.task_id == params.task_id]
        payload = {
            "lesson_slug": lesson_slug,
            "total": len(attempts),
            "attempts": [
                {
                    "task_id": item.task_id,
                    "attempt_no": item.attempt_no,
                    "status": item.status,
                    "verdict": item.verdict,
                    "created_at": (
                        item.created_time.strftime("%Y-%m-%d %H:%M:%S")
                        if item.created_time
                        else None
                    ),
                    "failed_assertions": _failed_assertions(item.assertions),
                }
                for item in attempts
            ],
        }
        return ToolExecution(ok=True, output=json.dumps(payload, ensure_ascii=False))


def _failed_assertions(raw: str | None) -> list[dict[str, str]]:
    """从落库的断言 JSON 里挑出没通过的条目（最多 MAX_TOOL_ASSERTIONS 条）。"""
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    failed: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "passed":
            continue
        failed.append(
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or "")[:120],
                "status": str(item.get("status") or ""),
                "detail": str(item.get("detail") or "")[:MAX_TOOL_ASSERTION_TEXT],
                "actual": str(item.get("actual") or "")[:MAX_TOOL_ASSERTION_TEXT],
            }
        )
        if len(failed) >= MAX_TOOL_ASSERTIONS:
            break
    return failed
