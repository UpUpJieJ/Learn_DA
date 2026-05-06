from openai import AsyncOpenAI

from app.sandbox import SandboxService
from app.sandbox.schemas import SandboxExecutionResult
from config.settings import settings

from .knowledge import KnowledgeRetriever, build_knowledge_block
from .prompts import build_chat_messages, build_explain_messages, build_fix_messages
from .results import parse_structured_result
from .intelligent_routing import IntelligentRouter, RoutingStrategy
from .schemas import (
    AgentChatData,
    AgentChatRequest,
    AgentRouteInfo,
    AgentRunVerification,
    ExplainCodeRequest,
    ExplainCodeResponse,
    FixCodeRequest,
    FixCodeResponse,
    ToolName,
)
from .tools import get_agent_tool


class AgentService:
    def __init__(
        self,
        sandbox_service: SandboxService | None = None,
        knowledge_retriever: KnowledgeRetriever | None = None,
        router: IntelligentRouter | None = None,
        routing_strategy: RoutingStrategy = RoutingStrategy.HYBRID,
    ) -> None:
        self.model = settings.effective_llm_model
        self.sandbox_service = sandbox_service or SandboxService()
        self.knowledge_retriever = knowledge_retriever or KnowledgeRetriever()
        self.router = router or IntelligentRouter(strategy=routing_strategy)

    def extract_user_message(self, payload: AgentChatRequest) -> str:
        if payload.message:
            return payload.message
        if payload.payload and payload.payload.message:
            return payload.payload.message
        return ""

    async def resolve_tool_name(self, message: str) -> ToolName:
        route = await self.router.resolve(message)
        return route.tool_name

    async def chat(self, payload: AgentChatRequest) -> AgentChatData:
        user_message = self.extract_user_message(payload)
        route = await self.router.resolve(user_message)
        tool_name = route.tool_name
        knowledge_block = await self._retrieve_knowledge(
            query=user_message,
            current_lesson=payload.context.current_lesson if payload.context else None,
        )
        messages = build_chat_messages(
            user_message=user_message,
            history=payload.history,
            context=payload.context,
            max_turns=settings.OPENAI_MAX_TURNS,
            tool_name=tool_name,
        )
        messages = self._inject_knowledge(messages, knowledge_block)
        content = await self._ask_llm(messages)
        if content:
            return AgentChatData(
                tool_name=tool_name,
                content=content,
                model=self.model,
                used_fallback=False,
                route=AgentRouteInfo(
                    tool_name=route.tool_name,
                    confidence=route.confidence,
                    reason=route.reason,
                    strategy=route.strategy.value,
                    matched_keyword=route.matched_keyword,
                ),
                structured_result=parse_structured_result(tool_name, content),
            )
        fallback_content = get_agent_tool(tool_name).fallback_content
        return AgentChatData(
            tool_name=tool_name,
            content=fallback_content,
            model=self.model,
            used_fallback=True,
            route=AgentRouteInfo(
                tool_name=route.tool_name,
                confidence=route.confidence,
                reason=route.reason,
                strategy=route.strategy.value,
                matched_keyword=route.matched_keyword,
            ),
            structured_result=parse_structured_result(tool_name, fallback_content),
        )

    async def fix_code(self, payload: FixCodeRequest) -> FixCodeResponse:
        knowledge_block = await self._retrieve_knowledge(
            query=f"{payload.error_message}\n{payload.code}",
            current_lesson=payload.context.current_lesson if payload.context else None,
        )
        content = await self._ask_llm(
            self._inject_knowledge(
                build_fix_messages(payload.code, payload.error_message, payload.context),
                knowledge_block,
            )
        )
        if content:
            fixed_code = self._extract_code_block(content) or payload.code
            return FixCodeResponse(
                fixed_code=fixed_code,
                explanation=content,
                model=self.model,
                used_fallback=False,
                verification=self._verify_fixed_code(fixed_code),
                structured_result=parse_structured_result("fix_code", content),
            )
        fallback_explanation = (
            "问题原因：\n"
            "我暂时无法连接模型。根据错误信息看，代码可能引用了尚未定义的变量或对象。\n\n"
            "修复方式：\n"
            "请先确认变量已经创建，再运行后续语句；如果变量来自上一段代码，需要把创建过程也放进当前代码。\n\n"
            "修复代码：\n"
            "```python\n"
            f"{payload.code}\n"
            "```\n\n"
            "验证建议：\n"
            "重新运行后，确认不再出现 NameError、ColumnNotFoundError 或类似的上下文缺失错误。"
        )
        return FixCodeResponse(
            fixed_code=payload.code,
            explanation=fallback_explanation,
            model=self.model,
            used_fallback=True,
            structured_result=parse_structured_result("fix_code", fallback_explanation),
        )

    async def explain_code(self, payload: ExplainCodeRequest) -> ExplainCodeResponse:
        knowledge_block = await self._retrieve_knowledge(
            query=payload.code,
            current_lesson=payload.context.current_lesson if payload.context else None,
        )
        content = await self._ask_llm(
            self._inject_knowledge(
                build_explain_messages(payload.code, payload.context),
                knowledge_block,
            )
        )
        if content:
            return ExplainCodeResponse(
                explanation=content,
                model=self.model,
                used_fallback=False,
                structured_result=parse_structured_result("explain_code", content),
            )
        fallback_explanation = (
            "结论：\n"
            "我暂时无法连接模型。这段代码会按顺序执行 Python 语句；如果包含 Polars 或 DuckDB API，"
            "通常是在完成数据读取、转换、查询和输出。\n\n"
            "关键步骤：\n"
            "1. 先看数据对象是如何创建或读取的。\n"
            "2. 再看 select、filter、group_by、sql 等 API 如何改变结果。\n"
            "3. 最后看 print、collect 或查询结果如何输出。\n\n"
            "容易混淆：\n"
            "Polars LazyFrame 需要 collect() 才会真正执行，DuckDB SQL 则通常通过 execute/sql 后取结果。\n\n"
            "建议你试试：\n"
            "把其中一个筛选条件或列名改掉，再观察输出或报错如何变化。"
        )
        return ExplainCodeResponse(
            explanation=fallback_explanation,
            model=self.model,
            used_fallback=True,
            structured_result=parse_structured_result("explain_code", fallback_explanation),
        )

    async def _ask_llm(self, messages: list[dict[str, str]]) -> str | None:
        api_key = settings.effective_llm_api_key
        if not api_key:
            return None

        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=settings.effective_llm_base_url,
            )
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
            )
        except Exception:
            return None

        if not response.choices:
            return None
        message = response.choices[0].message
        return message.content if message else None

    async def _retrieve_knowledge(
        self,
        query: str,
        current_lesson: str | None,
    ) -> str:
        chunks = await self.knowledge_retriever.search(
            query=query,
            current_lesson=current_lesson,
            limit=3,
        )
        return build_knowledge_block(chunks)

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

    def _verify_fixed_code(self, code: str) -> AgentRunVerification:
        try:
            result = self.sandbox_service.execute(code)
        except Exception as exc:
            return AgentRunVerification(
                verified=False,
                status="error",
                stdout="",
                stderr=str(exc),
                execution_time=0,
                used_sandbox="none",
            )

        return self._verification_from_result(result)

    def _verification_from_result(
        self,
        result: SandboxExecutionResult,
    ) -> AgentRunVerification:
        return AgentRunVerification(
            verified=result.status == "success",
            status=result.status,
            stdout=result.stdout,
            stderr=result.stderr,
            execution_time=result.execution_time,
            used_sandbox=result.used_sandbox,
        )

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
        return content[body_start + 1 : end].strip()
