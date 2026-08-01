import inspect
from typing import TYPE_CHECKING
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
    from app.practice.service import PracticeService

    from .repository import AgentInteractionRepository

from .evidence import (
    AgentEvidenceResolver,
    AgentLearningEvidence,
    build_teaching_feedback,
    derive_next_action,
)
from .knowledge import KnowledgeRetriever, build_knowledge_block
from .fc_tools import FC_TOOLS, FCToolExecutor
from .llm_client import LLMClient, LLMResult
from .prompts import build_chat_messages, build_evidence_block, build_fc_chat_messages
from .routing import AgentRouter
from .schemas import (
    AgentChatData,
    AgentChatRequest,
    AgentContext,
    AgentFeedbackRequest,
    AgentFeedbackResponse,
    ToolName,
)
from .tools import get_agent_tool


class AgentService:
    def __init__(
        self,
        knowledge_retriever: KnowledgeRetriever | None = None,
        router: AgentRouter | None = None,
        recommendation_service: RecommendationService | None = None,
        learner_state_service: "LearnerStateService | None" = None,
        analytics_service: "AnalyticsService | None" = None,
        practice_service: "PracticeService | None" = None,
        llm_client: AsyncOpenAI | None = None,
        interaction_repo: "AgentInteractionRepository | None" = None,
    ) -> None:
        self.model = settings.effective_llm_model
        # 运行时由 router 依赖注入 lifespan 共享的 retriever（避免每请求重建）；
        # 默认自建仅供单测直接构造 AgentService 时使用。
        self.knowledge_retriever = knowledge_retriever or KnowledgeRetriever()
        self.router = router or AgentRouter()
        self.recommendation_service = recommendation_service
        self.learner_state_service = learner_state_service
        self.analytics_service = analytics_service
        self.practice_service = practice_service
        self.interaction_repo = interaction_repo
        self._reserved_interaction = None
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
        if not created:
            return self._duplicate_response(evidence, payload, interaction_id)
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
                hint_level=self._estimate_hint_level(payload),
            )
            return AgentChatData(
                content=result.content,
                model=self.model,
                used_fallback=False,
                interaction_id=interaction_id,
                teaching_feedback=self._maybe_feedback(evidence, payload),
            )
        fallback_content = get_agent_tool(tool_name).fallback_content
        interaction_id = await self._persist_interaction(
            visitor_id=visitor_id or "",
            evidence=evidence,
            route=tool_name,
            retrieval_mode=getattr(
                self.knowledge_retriever, "last_retrieval_mode", None
            ),
            fallback_reason=result.error_reason,
            hint_level=self._estimate_hint_level(payload),
        )
        return AgentChatData(
            content=fallback_content,
            model=self.model,
            used_fallback=True,
            fallback_reason=result.error_reason,
            interaction_id=interaction_id,
            teaching_feedback=self._maybe_feedback(evidence, payload),
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
            practice_service=self.practice_service,
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
        if not created:
            return self._duplicate_response(evidence, payload, interaction_id)

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
                    hint_level=self._estimate_hint_level(payload),
                )
                return AgentChatData(
                    content=result.content,
                    model=self.model,
                    used_fallback=False,
                    interaction_id=interaction_id,
                    teaching_feedback=self._maybe_feedback(evidence, payload),
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
        interaction_id = await self._persist_interaction(
            visitor_id=visitor_id,
            evidence=evidence,
            route=tool_name,
            retrieval_mode=getattr(
                self.knowledge_retriever, "last_retrieval_mode", None
            ),
            tool_names=executor.called_tools,
            fallback_reason=fallback_reason,
            hint_level=self._estimate_hint_level(payload),
        )
        return AgentChatData(
            content=fallback_content,
            model=self.model,
            used_fallback=True,
            fallback_reason=fallback_reason,
            interaction_id=interaction_id,
            teaching_feedback=self._maybe_feedback(evidence, payload),
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

    async def _inject_evidence(
        self,
        messages: list[dict[str, str]],
        payload: AgentChatRequest,
        visitor_id: str | None,
    ) -> tuple[list[dict[str, str]], AgentLearningEvidence | None]:
        """解析服务端练习证据并注入 system 证据块。

        返回 (注入后的 messages, 解析出的 evidence)。无 practice_service 或
        无 visitor_id 时跳过（单测直接构造 AgentService 场景，或降级路径未带
        身份），不阻断回答，evidence 为 None。证据块插入在 system prompt 之后、
        history 之前，确保模型在生成回答前已看到权威练习状态。
        """
        if self.practice_service is None or not visitor_id:
            return messages, None
        lesson_slug = (
            payload.context.current_lesson if payload.context else None
        )
        attempt_id = (
            payload.context.attempt_id if payload.context else None
        )
        resolver = AgentEvidenceResolver(
            practice_repo=self.practice_service.repo,
            learner_state_service=self.learner_state_service,
        )
        try:
            evidence = await resolver.resolve(
                visitor_id=visitor_id,
                lesson_slug=lesson_slug,
                attempt_id=attempt_id,
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
    def _estimate_hint_level(payload: AgentChatRequest) -> int:
        """根据对话历史估算分级提示层级（连续求助逐级升高）。

        Task 3 将持久化 AgentInteraction 后可改为按真实连续求助计数；
        此处以当前请求 history 中的 user 消息数作为近似代理：
        0-1 条 -> Level 1，2-3 条 -> Level 2，4+ 条 -> Level 3。
        """
        user_turns = sum(1 for m in payload.history if m.role == "user")
        return max(1, min(3, 1 + user_turns // 2))

    def _maybe_feedback(
        self,
        evidence: AgentLearningEvidence | None,
        payload: AgentChatRequest,
    ) -> "TeachingFeedback | None":
        """有证据时构造结构化教学反馈；无证据时返回 None。"""
        if evidence is None:
            return None
        return build_teaching_feedback(
            evidence, hint_level=self._estimate_hint_level(payload)
        )

    def _duplicate_response(
        self,
        evidence: AgentLearningEvidence | None,
        payload: AgentChatRequest,
        interaction_id: int | None,
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
            teaching_feedback=self._maybe_feedback(evidence, payload),
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
                verification_status=(
                    evidence.verification_status if evidence else None
                ),
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
