from dataclasses import dataclass
from enum import Enum
from typing import Optional

from openai import AsyncOpenAI

from app.agent.schemas import ToolName
from config.settings import settings


class RoutingStrategy(Enum):
    KEYWORD = "keyword"
    LLM = "llm"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class AgentRoute:
    tool_name: ToolName
    confidence: float
    reason: str
    strategy: RoutingStrategy
    matched_keyword: Optional[str] = None


SYSTEM_ROUTING_PROMPT = """你是 Learn DA 的意图分类器，负责将用户消息分类到最适合的工具。

可用工具：
- generate_example_code：用户询问或请求示例代码、示范代码，提到具体的技术（polars/duckdb/sql）
- generate_exercise：用户要求生成练习题目、测试题、练习题
- fix_code：用户提到代码报错、错误、error、fix，或需要修复代码
- explain_code：用户要求解释代码、理解代码、说明代码作用
- suggest_next_step：用户问下一步学什么、接下来怎么做、继续学习
- general_chat：其他通用学习对话

必须严格按照 JSON 格式输出，字段：
- tool_name：选择的工具名
- confidence：0-1 的置信度
- reason：简短的分类理由
"""


class IntelligentRouter:
    def __init__(
        self,
        strategy: RoutingStrategy = RoutingStrategy.HYBRID,
        fallback_to_keyword: bool = True,
    ):
        self.strategy = strategy
        self.fallback_to_keyword = fallback_to_keyword
        self._keyword_rules = self._build_keyword_rules()

    def _build_keyword_rules(self) -> tuple[tuple[ToolName, tuple[str, ...], float, str], ...]:
        return (
            ("fix_code", ("报错", "错误", "error", "fix", "修复"), 0.88, "用户正在排查代码错误或请求修复"),
            ("explain_code", ("解释", "explain", "作用", "什么意思"), 0.82, "用户希望理解代码或概念"),
            ("generate_exercise", ("练习", "exercise", "题目", "出题"), 0.82, "用户希望生成练习任务"),
            ("suggest_next_step", ("下一步", "next step", "继续学", "学什么", "接下来"), 0.82, "用户希望获得学习路径建议"),
            ("generate_example_code", ("duckdb", "polars", "示例", "example", "代码"), 0.72, "用户希望获得数据分析示例或代码"),
        )

    async def resolve(self, message: str) -> AgentRoute:
        if self.strategy == RoutingStrategy.KEYWORD:
            return self._keyword_resolve(message)
        elif self.strategy == RoutingStrategy.LLM:
            return await self._llm_resolve(message)
        else:
            return await self._hybrid_resolve(message)

    def _keyword_resolve(self, message: str) -> AgentRoute:
        text = message.lower()
        for tool_name, keywords, confidence, reason in self._keyword_rules:
            matched_keyword = self._first_match(text, keywords)
            if matched_keyword:
                return AgentRoute(
                    tool_name=tool_name,
                    confidence=confidence,
                    reason=reason,
                    strategy=RoutingStrategy.KEYWORD,
                    matched_keyword=matched_keyword,
                )
        return AgentRoute(
            tool_name="general_chat",
            confidence=0.45,
            reason="未命中明确工具意图，使用通用学习助手回复",
            strategy=RoutingStrategy.KEYWORD,
            matched_keyword=None,
        )

    async def _llm_resolve(self, message: str) -> AgentRoute:
        api_key = settings.effective_llm_api_key
        base_url = settings.effective_llm_base_url
        if not api_key or not base_url:
            if self.fallback_to_keyword:
                return self._keyword_resolve(message)
            return AgentRoute(
                tool_name="general_chat",
                confidence=0.5,
                reason="LLM 不可用，使用默认路由",
                strategy=RoutingStrategy.KEYWORD,
            )

        try:
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            response = await client.chat.completions.create(
                model=settings.effective_llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM_ROUTING_PROMPT},
                    {"role": "user", "content": f"用户消息：{message}"},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            import json

            result = json.loads(response.choices[0].message.content or "{}")
            tool_name = result.get("tool_name", "general_chat")
            if tool_name not in {
                "generate_example_code",
                "generate_exercise",
                "fix_code",
                "explain_code",
                "suggest_next_step",
                "general_chat",
            }:
                tool_name = "general_chat"
            return AgentRoute(
                tool_name=tool_name,
                confidence=result.get("confidence", 0.7),
                reason=result.get("reason", "LLM 分类结果"),
                strategy=RoutingStrategy.LLM,
            )
        except Exception:
            if self.fallback_to_keyword:
                return self._keyword_resolve(message)
            return AgentRoute(
                tool_name="general_chat",
                confidence=0.5,
                reason="LLM 路由失败，使用默认路由",
                strategy=RoutingStrategy.KEYWORD,
            )

    async def _hybrid_resolve(self, message: str) -> AgentRoute:
        keyword_route = self._keyword_resolve(message)
        if keyword_route.tool_name != "general_chat" and keyword_route.confidence >= 0.8:
            return keyword_route
        return await self._llm_resolve(message)

    def _first_match(self, text: str, keywords: tuple[str, ...]) -> Optional[str]:
        for keyword in keywords:
            if keyword.lower() in text:
                return keyword
        return None
