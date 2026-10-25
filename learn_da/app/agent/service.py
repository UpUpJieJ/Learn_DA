import inspect
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator
from uuid import uuid4

from openai import AsyncOpenAI

from app.learning.repository import LearningRepository
from app.learning.recommendation import RecommendationService
from app.utils import log
from app.utils.logger import request_id_var
from config.settings import settings

if TYPE_CHECKING:
    from app.analytics.service import AnalyticsService
    from app.learner_state.service import LearnerStateService
    from app.workspace.repository import WorkspaceReadRepository

    from .repository import AgentInteractionRepository

from .evidence import (
    AgentEvidenceResolver,
    AgentLearningEvidence,
    build_teaching_feedback,
    derive_next_action,
)
from .knowledge import KnowledgeRetriever, build_knowledge_block
from .fc_tools import FC_TOOLS, FCToolExecutor
from .llm_client import LLMClient, LLMResult, LLMToolCall
from .prompts import (
    build_chat_messages,
    build_evidence_block,
    build_fc_chat_messages,
    build_hint_directive,
)
from .routing import AgentRouter
from .schemas import (
    AgentChatData,
    AgentChatRequest,
    AgentContext,
    AgentFeedbackRequest,
    AgentFeedbackResponse,
    ToolName,
)

FALLBACK_UNAVAILABLE_CONTENT = (
    "AI 助手暂时不可用（模型调用失败），这次我不会编造回答。\n\n"
    "你仍然可以用的：本次的服务端教学状态与任务判定结论已随响应返回"
    "（teachingFeedback），它来自真实提交记录，不是模型生成的；"
    "按提示在编辑器里改代码、重新提交，判定与进度照常记录。\n"
    "等网络或额度恢复后再来问我。"
)


class AgentService:
    def __init__(
        self,
        knowledge_retriever: KnowledgeRetriever | None = None,
        router: AgentRouter | None = None,
        recommendation_service: RecommendationService | None = None,
        learner_state_service: "LearnerStateService | None" = None,
        analytics_service: "AnalyticsService | None" = None,
        workspace_repo: "WorkspaceReadRepository | None" = None,
        llm_client: AsyncOpenAI | None = None,
        interaction_repo: "AgentInteractionRepository | None" = None,
    ) -> None:
        self.model = settings.LLM_MODEL
        # 运行时由 router 依赖注入 lifespan 共享的 retriever（避免每请求重建）；
        # 默认自建仅供单测直接构造 AgentService 时使用。
        self.knowledge_retriever = knowledge_retriever or KnowledgeRetriever()
        self.router = router or AgentRouter()
        self.recommendation_service = recommendation_service
        self.learner_state_service = learner_state_service
        self.analytics_service = analytics_service
        # 改版 M4：任务提交记录（task_attempts）是当前唯一的教学证据来源
        self.workspace_repo = workspace_repo
        self.interaction_repo = interaction_repo
        self._reserved_interaction = None
        # lifespan 共享的 LLM client；未注入时 _complete 自建临时 client 并负责关闭
        self.llm_client = llm_client

    def extract_user_message(self, payload: AgentChatRequest) -> str:
        """取出用户问题；纯空白视为没问（否则会白调一次模型）。"""
        if payload.message and payload.message.strip():
            return payload.message.strip()
        if payload.payload and payload.payload.message:
            if payload.payload.message.strip():
                return payload.payload.message.strip()
        return ""

    def resolve_tool_name(self, message: str) -> ToolName:
        return self.router.resolve(message).tool_name

    async def chat(
        self, payload: AgentChatRequest, visitor_id: str | None = None
    ) -> AgentChatData:
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
        # 阶段 3：注入服务端练习证据块（降级路径同样需要，保证事实来源一致）
        messages, evidence = await self._inject_evidence(messages, payload, visitor_id)
        interaction_id, created = await self._reserve_interaction(
            visitor_id=visitor_id or "", evidence=evidence
        )
        hint_level = await self._resolve_hint_level(payload, visitor_id, evidence)
        if not created:
            return self._duplicate_response(evidence, interaction_id, hint_level)
        messages = self._with_hint_directive(messages, hint_level)
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
            interaction_id = await self._persist_interaction(
                visitor_id=visitor_id or "",
                evidence=evidence,
                route=tool_name,
                retrieval_mode=getattr(
                    self.knowledge_retriever, "last_retrieval_mode", None
                ),
                llm_latency_ms=result.latency_ms,
                input_tokens=result.prompt_tokens,
                output_tokens=result.completion_tokens,
                fallback_reason=None,
                hint_level=hint_level,
            )
            return AgentChatData(
                content=result.content,
                model=self.model,
                used_fallback=False,
                interaction_id=interaction_id,
                teaching_feedback=self._maybe_feedback(evidence, hint_level),
            )
        fallback_content = self._fallback_chat_content(tool_name)
        interaction_id = await self._persist_interaction(
            visitor_id=visitor_id or "",
            evidence=evidence,
            route=tool_name,
            retrieval_mode=getattr(
                self.knowledge_retriever, "last_retrieval_mode", None
            ),
            fallback_reason=result.error_reason,
            hint_level=hint_level,
        )
        return AgentChatData(
            content=fallback_content,
            model=self.model,
            used_fallback=True,
            fallback_reason=result.error_reason,
            interaction_id=interaction_id,
            teaching_feedback=self._maybe_feedback(evidence, hint_level),
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
            workspace_repo=self.workspace_repo,
            current_lesson=current_lesson,
        )
        messages = build_fc_chat_messages(
            user_message=user_message,
            history=payload.history,
            context=payload.context,
            max_turns=settings.OPENAI_MAX_TURNS,
        )
        # 阶段 3：始终在 FC prompt 写入服务端证据块
        messages, evidence = await self._inject_evidence(messages, payload, visitor_id)
        interaction_id, created = await self._reserve_interaction(
            visitor_id=visitor_id, evidence=evidence
        )
        hint_level = await self._resolve_hint_level(payload, visitor_id, evidence)
        if not created:
            return self._duplicate_response(evidence, interaction_id, hint_level)

        max_rounds = settings.AGENT_FC_MAX_TOOL_ROUNDS
        messages = self._with_hint_directive(messages, hint_level)
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
                interaction_id = await self._persist_interaction(
                    visitor_id=visitor_id,
                    evidence=evidence,
                    route=tool_name,
                    retrieval_mode=getattr(
                        self.knowledge_retriever, "last_retrieval_mode", None
                    ),
                    tool_names=executor.called_tools,
                    llm_latency_ms=result.latency_ms,
                    input_tokens=result.prompt_tokens,
                    output_tokens=result.completion_tokens,
                    fallback_reason=None,
                    hint_level=hint_level,
                )
                return AgentChatData(
                    content=result.content,
                    model=self.model,
                    used_fallback=False,
                    interaction_id=interaction_id,
                    teaching_feedback=self._maybe_feedback(evidence, hint_level),
                )
            # 强制直答轮仍返回 tool_calls / 无有效内容：不再给机会
            break

        tool_name = self._derive_fc_tool_name(executor.called_tools)
        fallback_content = self._fallback_chat_content(tool_name)
        log.info(
            "[agent] fc_chat llm_calls={} tools_called={} tool_name={} "
            "used_fallback=True fallback_reason={}",
            llm_calls,
            executor.called_tools,
            tool_name,
            fallback_reason,
        )
        interaction_id = await self._persist_interaction(
            visitor_id=visitor_id,
            evidence=evidence,
            route=tool_name,
            retrieval_mode=getattr(
                self.knowledge_retriever, "last_retrieval_mode", None
            ),
            tool_names=executor.called_tools,
            fallback_reason=fallback_reason,
            hint_level=hint_level,
        )
        return AgentChatData(
            content=fallback_content,
            model=self.model,
            used_fallback=True,
            fallback_reason=fallback_reason,
            interaction_id=interaction_id,
            teaching_feedback=self._maybe_feedback(evidence, hint_level),
        )

    async def chat_stream(
        self,
        payload: AgentChatRequest,
        visitor_id: str,
    ) -> AsyncIterator[dict]:
        """流式版对话编排（E3）：边生成边下发，事件形状见 AgentStreamEvent。

        与 ``chat_with_tools`` 同一套约束（证据注入、幂等、分级提示、最多
        ``AGENT_FC_MAX_TOOL_ROUNDS`` 轮工具），区别只是**每一轮都用流式**：
        文本增量立刻下发，工具调用分片在轮末拼装完整后再执行。

        为什么每轮都流而不是只流最后一轮：模型决定「回答还是调工具」发生在
        同一轮输出里，非流式探测一轮就得多等一次完整往返（实测 1.7-3.9s）。
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
            workspace_repo=self.workspace_repo,
            current_lesson=current_lesson,
        )
        messages = build_fc_chat_messages(
            user_message=user_message,
            history=payload.history,
            context=payload.context,
            max_turns=settings.OPENAI_MAX_TURNS,
        )
        messages, evidence = await self._inject_evidence(
            messages, payload, visitor_id
        )
        interaction_id, created = await self._reserve_interaction(
            visitor_id=visitor_id, evidence=evidence
        )
        hint_level = await self._resolve_hint_level(
            payload, visitor_id, evidence
        )
        feedback = self._maybe_feedback(evidence, hint_level)

        if not created:
            duplicate = self._duplicate_response(
                evidence, interaction_id, hint_level
            )
            yield {"type": "delta", "text": duplicate.content}
            yield {"type": "done", "data": duplicate.model_dump(by_alias=True)}
            return

        max_rounds = settings.AGENT_FC_MAX_TOOL_ROUNDS
        messages = self._with_hint_directive(messages, hint_level)
        fallback_reason = "upstream_error"
        invalid_params_seen = False
        llm_calls = 0
        streamed_chars = 0

        for round_index in range(max_rounds + 1):
            force_answer = round_index >= max_rounds
            tool_choice = "none" if force_answer else "auto"
            round_text: list[str] = []
            tool_calls: tuple[LLMToolCall, ...] = ()
            error_reason: str | None = None
            interrupted = False
            latency_ms = 0
            prompt_tokens = None
            completion_tokens = None

            async with self._llm() as llm:
                async for event in llm.stream(
                    messages, tools=FC_TOOLS, tool_choice=tool_choice
                ):
                    if event.delta:
                        round_text.append(event.delta)
                        streamed_chars += len(event.delta)
                        yield {"type": "delta", "text": event.delta}
                    if event.done:
                        tool_calls = event.tool_calls
                        error_reason = event.error_reason
                        interrupted = event.interrupted
                        latency_ms = event.latency_ms
                        prompt_tokens = event.prompt_tokens
                        completion_tokens = event.completion_tokens
            llm_calls += 1

            text = "".join(round_text).strip()
            if interrupted and text:
                # 已吐字后中断：内容是学习者已经看到的那部分，保留它并明说
                # 不完整；绝不拿降级文案盖上去（那等于把他看到的字吞掉）。
                tool_name = self._derive_fc_tool_name(executor.called_tools)
                interaction_id = await self._persist_interaction(
                    visitor_id=visitor_id,
                    evidence=evidence,
                    route=tool_name,
                    retrieval_mode=getattr(
                        self.knowledge_retriever, "last_retrieval_mode", None
                    ),
                    tool_names=executor.called_tools,
                    llm_latency_ms=latency_ms,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    fallback_reason="stream_interrupted",
                    hint_level=hint_level,
                )
                yield {
                    "type": "error",
                    "reason": "stream_interrupted",
                    "partial": True,
                }
                data = AgentChatData(
                    content=text,
                    model=self.model,
                    used_fallback=True,
                    fallback_reason="stream_interrupted",
                    interaction_id=interaction_id,
                    teaching_feedback=feedback,
                )
                yield {"type": "done", "data": data.model_dump(by_alias=True)}
                return
            if error_reason:
                fallback_reason = error_reason
                break
            if tool_calls and not force_answer:
                # 工具轮：告诉前端正在查什么，避免长时间无反馈
                yield {
                    "type": "tool",
                    "names": [call.name for call in tool_calls],
                }
                assistant_message = self._assistant_tool_call_message(
                    LLMResult(
                        content=text or None,
                        error_reason=None,
                        latency_ms=latency_ms,
                        tool_calls=tool_calls,
                    )
                )
                messages.append(assistant_message)
                aborted = False
                for tool_call in tool_calls:
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
                            fallback_reason = "invalid_tool_params"
                            aborted = True
                        invalid_params_seen = True
                if aborted:
                    break
                continue
            if text:
                tool_name = self._derive_fc_tool_name(executor.called_tools)
                log.info(
                    "[agent] fc_chat_stream llm_calls={} tools_called={} "
                    "tool_name={} chars={} interrupted={}",
                    llm_calls,
                    executor.called_tools,
                    tool_name,
                    len(text),
                    interrupted,
                )
                interaction_id = await self._persist_interaction(
                    visitor_id=visitor_id,
                    evidence=evidence,
                    route=tool_name,
                    retrieval_mode=getattr(
                        self.knowledge_retriever, "last_retrieval_mode", None
                    ),
                    tool_names=executor.called_tools,
                    llm_latency_ms=latency_ms,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    fallback_reason=None,
                    hint_level=hint_level,
                )
                data = AgentChatData(
                    content=text,
                    model=self.model,
                    used_fallback=False,
                    interaction_id=interaction_id,
                    teaching_feedback=feedback,
                )
                yield {"type": "done", "data": data.model_dump(by_alias=True)}
                return
            # 强制直答轮仍无有效内容：不再给机会
            break

        tool_name = self._derive_fc_tool_name(executor.called_tools)
        fallback_content = self._fallback_chat_content(tool_name)
        log.info(
            "[agent] fc_chat_stream llm_calls={} tools_called={} tool_name={} "
            "used_fallback=True fallback_reason={} streamed_chars={}",
            llm_calls,
            executor.called_tools,
            tool_name,
            fallback_reason,
            streamed_chars,
        )
        interaction_id = await self._persist_interaction(
            visitor_id=visitor_id,
            evidence=evidence,
            route=tool_name,
            retrieval_mode=getattr(
                self.knowledge_retriever, "last_retrieval_mode", None
            ),
            tool_names=executor.called_tools,
            fallback_reason=fallback_reason,
            hint_level=hint_level,
        )
        if streamed_chars:
            # 已经吐过字，不能再补一段「不可用」的假回答盖上去
            yield {
                "type": "error",
                "reason": fallback_reason,
                "partial": True,
            }
            data = AgentChatData(
                content=fallback_content,
                model=self.model,
                used_fallback=True,
                fallback_reason=fallback_reason,
                interaction_id=interaction_id,
                teaching_feedback=feedback,
            )
            yield {"type": "done", "data": data.model_dump(by_alias=True)}
            return
        yield {"type": "delta", "text": fallback_content}
        data = AgentChatData(
            content=fallback_content,
            model=self.model,
            used_fallback=True,
            fallback_reason=fallback_reason,
            interaction_id=interaction_id,
            teaching_feedback=feedback,
        )
        yield {"type": "done", "data": data.model_dump(by_alias=True)}

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
        async with self._llm() as llm:
            return await llm.complete(messages, tools=tools, tool_choice=tool_choice)

    @asynccontextmanager
    async def _llm(self) -> AsyncIterator[LLMClient]:
        """按需给出 LLMClient：共享 client 直通，否则自建并在退出时关闭。"""
        if self.llm_client is not None:
            yield LLMClient(client=self.llm_client, model=self.model)
            return

        api_key = settings.LLM_API_KEY
        if not api_key:
            yield LLMClient(client=None, model=self.model)
            return

        temp_client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.LLM_BASE_URL,
        )
        try:
            yield LLMClient(client=temp_client, model=self.model)
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

    async def _inject_evidence(
        self,
        messages: list[dict[str, str]],
        payload: AgentChatRequest,
        visitor_id: str | None,
    ) -> tuple[list[dict[str, str]], AgentLearningEvidence | None]:
        """解析服务端任务证据并注入 system 证据块。

        返回 (注入后的 messages, 解析出的 evidence)。无 workspace_repo 或
        无 visitor_id 时跳过（单测直接构造 AgentService 场景，或降级路径未带
        身份），不阻断回答，evidence 为 None。证据块插入在 system prompt 之后、
        history 之前，确保模型在生成回答前已看到权威任务状态。
        """
        if self.workspace_repo is None:
            return messages, None
        if not visitor_id:
            return messages, None
        lesson_slug = (
            payload.context.current_lesson if payload.context else None
        )
        attempt_id = (
            payload.context.attempt_id if payload.context else None
        )
        task_id = payload.context.current_task if payload.context else None
        editor_code = payload.context.current_code if payload.context else None
        resolver = AgentEvidenceResolver(workspace_repo=self.workspace_repo)
        try:
            evidence = await resolver.resolve(
                visitor_id=visitor_id,
                lesson_slug=lesson_slug,
                attempt_id=attempt_id,
                task_id=task_id,
                editor_code=editor_code,
            )
        except Exception:
            log.exception("[agent] evidence 解析失败，跳过证据块注入")
            return messages, None
        return self._prepend_evidence_block(messages, evidence), evidence

    @staticmethod
    def _prepend_evidence_block(
        messages: list[dict[str, str]],
        evidence: AgentLearningEvidence,
    ) -> list[dict[str, str]]:
        block = build_evidence_block(evidence)
        if not block:
            return messages
        return [
            messages[0],
            {"role": "system", "content": block},
            *messages[1:],
        ]

    @staticmethod
    def _with_hint_directive(
        messages: list[dict[str, str]],
        hint_level: int | None,
    ) -> list[dict[str, str]]:
        """把服务端算出的提示层级作为一条 system 指令插到提问之前。

        层级在 ``_resolve_hint_level`` 里依赖证据（课程 slug）才能算，晚于
        证据块注入，所以单独补一条，而不是塞回证据块。没有层级时原样返回。
        """
        line = build_hint_directive(hint_level)
        if not line:
            return messages
        if not messages:
            return messages
        return [*messages[:-1], {"role": "system", "content": line}, messages[-1]]

    @staticmethod
    def _estimate_hint_level(payload: AgentChatRequest) -> int:
        """降级路径：用客户端 history 的 user 消息数估算分级提示层级。

        仅在服务端任务失败计数不可用（无 repo/身份/课程/任务，或查询失败）
        时作为近似；权威来源见 _resolve_hint_level。
        0-1 条 -> Level 1，2-3 条 -> Level 2，4+ 条 -> Level 3。
        """
        user_turns = sum(1 for m in payload.history if m.role == "user")
        return max(1, min(3, 1 + user_turns // 2))

    async def _resolve_hint_level(
        self,
        payload: AgentChatRequest,
        visitor_id: str | None,
        evidence: AgentLearningEvidence | None,
    ) -> int:
        """分级提示层级：按服务端真实失败次数算，不再数「问了几次」。

        改版 E2 起与阶梯提示同一口径：
        ``level = min(3, 1 + failures_since_last_hint + hints_used)``
        —— 失败次数来自 ``task_attempts``（任务级），已用层数来自
        ``hint_usages``。旧口径（按该课提问次数 1-2/3-4/5+）有双向错误：
        连问几个概念问题就升到 L3（没卡住的人拿到近答案），而连续失败却
        从不提问的人永远停在 L1（真卡住的人拿不到有效帮助）。

        无任务级证据（无 repo/身份/课程/任务，或查询失败）时降级为
        history 估算。
        """
        lesson_slug = evidence.lesson_slug if evidence else None
        task_id = (evidence.task_id if evidence else None) or (
            payload.context.current_task if payload.context else None
        )
        if self.workspace_repo is not None and visitor_id and lesson_slug and task_id:
            try:
                state = await self.workspace_repo.hint_state(
                    visitor_id, lesson_slug, task_id
                )
                return state.level
            except Exception:
                log.exception("[agent] 任务失败计数查询失败，降级为 history 估算")
        return self._estimate_hint_level(payload)

    def _maybe_feedback(
        self,
        evidence: AgentLearningEvidence | None,
        hint_level: int | None,
    ) -> "TeachingFeedback | None":
        """有证据时构造结构化教学反馈；无证据时返回 None。"""
        if evidence is None:
            return None
        return build_teaching_feedback(evidence, hint_level=hint_level or 1)

    def _duplicate_response(
        self,
        evidence: AgentLearningEvidence | None,
        interaction_id: int | None,
        hint_level: int | None,
    ) -> AgentChatData:
        """避免同一 request ID 重放时再次调用模型。

        审计表不保存完整模型正文，因此重放只返回稳定提示，而不是伪造原始
        回答；调用方仍可使用 interactionId 关联上一条交互和反馈。
        """
        return AgentChatData(
            content="这次请求已经处理过，请查看上一条回答。",
            model=self.model,
            used_fallback=True,
            fallback_reason="duplicate_request",
            interaction_id=interaction_id,
            teaching_feedback=self._maybe_feedback(evidence, hint_level),
        )

    # ── 阶段 3 Task 3：交互审计与 ai_help 关联 ───────────────

    async def _reserve_interaction(
        self,
        *,
        visitor_id: str,
        evidence: AgentLearningEvidence | None,
    ) -> tuple[int | None, bool]:
        """在调用模型前预留 request ID，返回 (interaction_id, created)。

        没有请求上下文时保持单测和内部调用的既有行为。数据库不可用时不阻断
        对话，但会放弃本次幂等保护并记录日志。
        """
        if self.interaction_repo is None or not visitor_id:
            return None, True
        req_id = request_id_var.get()
        if not req_id or req_id == "-":
            return None, True

        try:
            interaction, created = await self.interaction_repo.get_or_create(
                visitor_id=visitor_id,
                request_id=req_id,
                lesson_slug=evidence.lesson_slug if evidence else None,
                attempt_id=evidence.attempt_id if evidence else None,
            )
            if created:
                # 先在当前事务中保留行；模型完成后与 ai_help、指标一起提交。
                # 这样不会在共享测试 session 或请求事务中途提交。
                self._reserved_interaction = (req_id, interaction)
            return interaction.id, created
        except Exception:
            await self._rollback_interaction()
            log.exception("[agent] interaction 预留失败，已忽略幂等保护")
            return None, True

    async def _persist_interaction(
        self,
        *,
        visitor_id: str,
        evidence: AgentLearningEvidence | None,
        route: str | None = None,
        retrieval_mode: str | None = None,
        tool_names: list[str] | None = None,
        llm_latency_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        fallback_reason: str | None = None,
        hint_level: int | None = None,
    ) -> int | None:
        """幂等创建交互审计并回填指标；同 request_id 重放不重复计入 ai_help。

        失败时只记日志，绝不把一次成功的 Agent 回答变成 500（埋点是旁路
        副作用，LLM 调用已经发生且已计费）。
        """
        if self.interaction_repo is None or not visitor_id:
            return None
        req_id = request_id_var.get()
        if not req_id or req_id == "-":
            # 未经过请求中间件（如单测直接调用），不持久化
            return None
        lesson_slug = evidence.lesson_slug if evidence else None
        attempt_id = evidence.attempt_id if evidence else None
        try:
            reserved = self._reserved_interaction
            if reserved is not None and reserved[0] == req_id:
                interaction, created = reserved[1], True
            else:
                interaction, created = await self.interaction_repo.get_or_create(
                    visitor_id=visitor_id,
                    request_id=req_id,
                    lesson_slug=lesson_slug,
                    attempt_id=attempt_id,
                )
        except Exception:
            log.exception("[agent] interaction 创建失败，已忽略")
            return None
        # 仅新创建时写 ai_help，保证相同 request_id 重放不重复计数
        if created:
            await self._track_ai_help(visitor_id, req_id, evidence)
        # 回填可观测指标（不持久化完整 prompt / 代码 / token / cookie）
        try:
            await self.interaction_repo.fill_metrics(
                interaction,
                route=route,
                retrieval_mode=retrieval_mode,
                tool_names=tool_names,
                llm_latency_ms=llm_latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                fallback_reason=fallback_reason,
                evidence_state=evidence.state if evidence else None,
                verification_status=None,
                hint_level=hint_level,
                next_action=(
                    derive_next_action(evidence) if evidence else None
                ),
            )
        except Exception:
            log.exception("[agent] interaction 指标回填失败，已忽略")
        self._reserved_interaction = None
        await self._commit_interaction()
        return interaction.id

    async def _commit_interaction(self) -> None:
        if self.interaction_repo is None:
            return
        db = getattr(self.interaction_repo, "db", None)
        if getattr(db, "info", {}).get("external_transaction"):
            return
        commit = getattr(db, "commit", None)
        if not callable(commit):
            return
        result = commit()
        if inspect.isawaitable(result):
            await result

    async def _rollback_interaction(self) -> None:
        if self.interaction_repo is None:
            return
        db = getattr(self.interaction_repo, "db", None)
        rollback = getattr(db, "rollback", None)
        if not callable(rollback):
            return
        result = rollback()
        if inspect.isawaitable(result):
            await result

    async def _track_ai_help(
        self,
        visitor_id: str,
        req_id: str,
        evidence: AgentLearningEvidence | None,
    ) -> None:
        """在同一事务写 ai_help 事件；lesson 来自 evidence resolver。"""
        if self.analytics_service is None:
            return
        from app.analytics.schemas import EventTrackRequest, EventType

        lesson_slug = evidence.lesson_slug if evidence else None
        try:
            await self.analytics_service.track_event(
                EventTrackRequest.model_validate(
                    {
                        "eventType": EventType.AI_HELP.value,
                        "lessonSlug": lesson_slug,
                        "eventId": f"ai_help:{visitor_id}:{req_id}",
                    }
                ),
                visitor_id=visitor_id,
                commit=False,
            )
        except Exception:
            log.exception("[agent] ai_help 埋点写入失败，已忽略以保全聊天响应")

    async def record_feedback(
        self,
        req: AgentFeedbackRequest,
        visitor_id: str,
    ) -> AgentFeedbackResponse:
        """记录用户对某次交互的反馈（upsert，不新增 ai_help）。"""
        if self.interaction_repo is None:
            return AgentFeedbackResponse(recorded=False, interaction_id=req.interaction_id)
        interaction = await self.interaction_repo.get_by_id(
            req.interaction_id, visitor_id
        )
        if interaction is None:
            return AgentFeedbackResponse(
                recorded=False, interaction_id=req.interaction_id
            )
        await self.interaction_repo.update_feedback(interaction, req.feedback)
        await self._commit_interaction()
        return AgentFeedbackResponse(
            recorded=True, interaction_id=interaction.id
        )

    def _fallback_chat_content(self, tool_name: ToolName) -> str:
        """模型不可用时的回答（2026-10-23 决策：明说不可用，不编造）。

        以前这里返回按意图预置的确定性话术，看起来像"AI 答了"，但内容与用户
        当前代码无关，容易被当成真的教学判断。现在统一明说不可用，并说明
        服务端教学状态（teachingFeedback）仍然可信、仍随响应返回。

        ``tool_name`` 保留在签名里，便于将来按意图做真正有依据的兜底。
        """
        return FALLBACK_UNAVAILABLE_CONTENT

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
