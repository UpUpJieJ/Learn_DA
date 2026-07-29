"""受限 Function Calling 工具集（阶段 ④ Task 4.1）。

红线（见计划设计决策表）：
- 只提供三个只读工具，不存在任何执行/写入类工具；
- visitor_id 由服务端注入，不作为模型可控参数；
- get_recommendation 只读规则引擎结果，模型不得改排序。

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
]


class SearchKnowledgeParams(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class EmptyParams(BaseModel):
    model_config = {"extra": "ignore"}


_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "search_knowledge": SearchKnowledgeParams,
    "get_learner_progress": EmptyParams,
    "get_recommendation": EmptyParams,
}


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
        current_lesson: str | None = None,
    ) -> None:
        self.knowledge_retriever = knowledge_retriever
        self.visitor_id = visitor_id
        self.learner_state_service = learner_state_service
        self.recommendation_service = recommendation_service
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
        if self.learner_state_service is None:
            return ToolExecution(
                ok=False,
                output=json.dumps(
                    {"error": "unavailable", "message": "学习进度服务不可用"},
                    ensure_ascii=False,
                ),
            )
        completed = await self.learner_state_service.get_completed_lessons(
            self.visitor_id
        )
        last_visited = await self.learner_state_service.get_last_visited(
            self.visitor_id
        )
        payload = {"completed_lessons": completed, "last_visited": last_visited}
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
