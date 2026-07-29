from typing import TYPE_CHECKING
from uuid import uuid4

from openai import AsyncOpenAI

from app.learning.repository import LearningRepository
from app.learning.recommendation import RecommendationService
from app.utils import log
from config.settings import settings

if TYPE_CHECKING:
    from app.analytics.service import AnalyticsService
    from app.learner_state.service import LearnerStateService

from .knowledge import KnowledgeRetriever, build_knowledge_block
from .fc_tools import FC_TOOLS, FCToolExecutor
from .llm_client import LLMClient, LLMResult
from .prompts import build_chat_messages, build_fc_chat_messages
from .routing import AgentRouter
from .schemas import AgentChatData, AgentChatRequest, AgentContext, ToolName
from .tools import get_agent_tool


class AgentService:
    def __init__(
        self,
        knowledge_retriever: KnowledgeRetriever | None = None,
        router: AgentRouter | None = None,
        recommendation_service: RecommendationService | None = None,
        learner_state_service: "LearnerStateService | None" = None,
        analytics_service: "AnalyticsService | None" = None,
        llm_client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = settings.effective_llm_model
        # 运行时由 router 依赖注入 lifespan 共享的 retriever（避免每请求重建）；
        # 默认自建仅供单测直接构造 AgentService 时使用。
        self.knowledge_retriever = knowledge_retriever or KnowledgeRetriever()
        self.router = router or AgentRouter()
        self.recommendation_service = recommendation_service
        self.learner_state_service = learner_state_service
        self.analytics_service = analytics_service
        # lifespan 共享的 LLM client；未注入时 _complete 自建临时 client 并负责关闭
        self.llm_client = llm_client

    def extract_user_message(self, payload: AgentChatRequest) -> str:
        if payload.message:
            return payload.message
        if payload.payload and payload.payload.message:
            return payload.payload.message
        return ""

    def resolve_tool_name(self, message: str) -> ToolName:
        return self.router.resolve(message).tool_name

    async def chat(self, payload: AgentChatRequest) -> AgentChatData:
        user_message = self.extract_user_message(payload)
        route = self.router.resolve(user_message)
        tool_name = route.tool_name
        knowledge_block, knowledge_hits = await self._retrieve_knowledge(
            query=user_message,
            current_lesson=payload.context.current_lesson if payload.context else None,
        )
        messages = build_chat_messages(
            user_message=user_message,
            history=payload.history,
            context=payload.context,
            max_turns=settings.OPENAI_MAX_TURNS,
        )
        messages = self._inject_knowledge(messages, knowledge_block)
        result = await self._complete(messages)
        # 单次请求的路由/检索/LLM 指标通过 request_id 与 [llm] 日志串联
        log.info(
            "[agent] chat route={} confidence={} retrieval_mode={} "
            "knowledge_hits={} used_fallback={} fallback_reason={}",
            tool_name,
            route.confidence,
            getattr(self.knowledge_retriever,
                    "last_retrieval_mode", "unknown"),
            knowledge_hits,
            result.content is None,
            result.error_reason or "-",
        )
        if result.content:
            return AgentChatData(
                content=result.content,
                model=self.model,
                used_fallback=False,
            )
        fallback_content = get_agent_tool(tool_name).fallback_content
        return AgentChatData(
            content=fallback_content,
            model=self.model,
            used_fallback=True,
            fallback_reason=result.error_reason,
        )

    async def chat_with_tools(
        self,
        payload: AgentChatRequest,
        visitor_id: str,
    ) -> AgentChatData:
        """受限 Function Calling 编排循环（阶段 ④ Task 4.1）。

        硬约束：最多 AGENT_FC_MAX_TOOL_ROUNDS 轮工具调用，超限后强制
        tool_choice="none" 要求直接回答；非法工具参数只给一次重试机会，
        二次失败走确定性 fallback。单次请求最多 max_rounds+1 次 LLM 调用。
        """
        user_message = self.extract_user_message(payload)
        current_lesson = (
            payload.context.current_lesson if payload.context else None
        )
        if self.recommendation_service is None:
            self.recommendation_service = RecommendationService(
                repository=LearningRepository(),
                learner_state_service=self.learner_state_service,
            )
        executor = FCToolExecutor(
            knowledge_retriever=self.knowledge_retriever,
            visitor_id=visitor_id,
            learner_state_service=self.learner_state_service,
            recommendation_service=self.recommendation_service,
            current_lesson=current_lesson,
        )
        messages = build_fc_chat_messages(
            user_message=user_message,
            history=payload.history,
            context=payload.context,
            max_turns=settings.OPENAI_MAX_TURNS,
        )

        max_rounds = settings.AGENT_FC_MAX_TOOL_ROUNDS
        fallback_reason: str = "upstream_error"
        invalid_params_seen = False
        llm_calls = 0
        for round_index in range(max_rounds + 1):
            force_answer = round_index >= max_rounds
            result = await self._complete(
                messages,
                tools=FC_TOOLS,
                tool_choice="none" if force_answer else "auto",
            )
            llm_calls += 1
            if result.error_reason:
                fallback_reason = result.error_reason
                break
            if result.tool_calls and not force_answer:
                messages.append(self._assistant_tool_call_message(result))
                aborted = False
                for tool_call in result.tool_calls:
                    execution = await executor.execute(
                        tool_call.name, tool_call.arguments
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": execution.output,
                        }
                    )
                    if execution.invalid_params:
                        if invalid_params_seen:
                            # 一次重试机会已用完，二次非法参数直接降级
                            fallback_reason = "invalid_tool_params"
                            aborted = True
                        invalid_params_seen = True
                if aborted:
                    break
                continue
            if result.content:
                tool_name = self._derive_fc_tool_name(executor.called_tools)
                log.info(
                    "[agent] fc_chat llm_calls={} tools_called={} "
                    "tool_name={} used_fallback=False",
                    llm_calls,
                    executor.called_tools,
                    tool_name,
                )
                return AgentChatData(
                    content=result.content,
                    model=self.model,
                    used_fallback=False,
                )
            # 强制直答轮仍返回 tool_calls / 无有效内容：不再给机会
            break

        tool_name = self._derive_fc_tool_name(executor.called_tools)
        fallback_content = get_agent_tool(tool_name).fallback_content
        log.info(
            "[agent] fc_chat llm_calls={} tools_called={} tool_name={} "
            "used_fallback=True fallback_reason={}",
            llm_calls,
            executor.called_tools,
            tool_name,
            fallback_reason,
        )
        return AgentChatData(
            content=fallback_content,
            model=self.model,
            used_fallback=True,
            fallback_reason=fallback_reason,
        )

    @staticmethod
    def _assistant_tool_call_message(result: LLMResult) -> dict:
        return {
            "role": "assistant",
            "content": result.content or "",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    },
                }
                for tool_call in result.tool_calls
            ],
        }

    @staticmethod
    def _derive_fc_tool_name(called_tools: list[str]) -> ToolName:
        """意图标签取自模型调用过的工具，不再从正文抠标签。"""
        if "get_recommendation" in called_tools:
            return "suggest_next_step"
        return "general_chat"

    async def _complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> LLMResult:
        """统一 LLM 调用入口：走 LLMClient 适配器（超时/重试/错误分类）。

        优先复用 lifespan 注入的共享 client；未注入时（单测直接构造等）
        自建临时 client 并在调用后关闭，无 key 则确定性返回 no_api_key。
        """
        if self.llm_client is not None:
            return await LLMClient(
                client=self.llm_client, model=self.model
            ).complete(messages, tools=tools, tool_choice=tool_choice)

        api_key = settings.effective_llm_api_key
        if not api_key:
            return await LLMClient(client=None, model=self.model).complete(
                messages, tools=tools, tool_choice=tool_choice
            )

        temp_client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.effective_llm_base_url,
        )
        try:
            return await LLMClient(
                client=temp_client, model=self.model
            ).complete(messages, tools=tools, tool_choice=tool_choice)
        finally:
            # 共享 client 由 lifespan 统一关闭，这里只回收自建的临时 client
            try:
                await temp_client.close()
            except Exception:
                pass

    async def _retrieve_knowledge(
        self,
        query: str,
        current_lesson: str | None,
    ) -> tuple[str, int]:
        chunks = await self.knowledge_retriever.search(
            query=query,
            current_lesson=current_lesson,
            limit=3,
        )
        return build_knowledge_block(chunks), len(chunks)

    def _inject_knowledge(
        self,
        messages: list[dict[str, str]],
        knowledge_block: str,
    ) -> list[dict[str, str]]:
        if not knowledge_block:
            return messages
        return [
            messages[0],
            {"role": "system", "content": knowledge_block},
            *messages[1:],
        ]

    def _fallback_chat_content(self, tool_name: ToolName) -> str:
        return get_agent_tool(tool_name).fallback_content

    def _extract_code_block(self, content: str) -> str | None:
        marker = "```"
        start = content.find(marker)
        if start == -1:
            return None
        body_start = content.find("\n", start)
        if body_start == -1:
            return None
        end = content.find(marker, body_start + 1)
        if end == -1:
            return None
        return content[body_start + 1: end].strip()

    @staticmethod
    def _split_guidance_content(content: str) -> tuple[str, str | None]:
        explanation_label = "解释建议："
        exercise_label = "下一步练习："
        normalized = content.strip()

        if exercise_label not in normalized:
            return normalized.removeprefix(explanation_label).strip(), None

        explanation, exercise = normalized.split(exercise_label, 1)
        return (
            explanation.removeprefix(explanation_label).strip(),
            exercise.strip() or None,
        )

    @staticmethod
    def _fallback_recommendation_explanation(recommendation) -> str:
        if recommendation is None:
            return (
                "当前没有明确推荐。你可以继续当前课程，或从课程列表中选择"
                "一个最想巩固的主题。"
            )
        return (
            f"建议你学习《{recommendation.target_title}》。"
            f"规则依据是：{recommendation.reason}"
        )

    @staticmethod
    def _fallback_recommendation_exercise(recommendation) -> str:
        if recommendation is None:
            return "选择当前课程中的一个示例，修改一个输入值并解释输出变化。"
        return (
            f"打开《{recommendation.target_title}》，选择一个示例修改输入或条件，"
            "先预测结果，再运行代码验证。"
        )
