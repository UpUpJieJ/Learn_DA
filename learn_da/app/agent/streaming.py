import asyncio
import json
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI

from app.agent.intelligent_routing import AgentRoute
from app.agent.knowledge import build_knowledge_block
from app.agent.prompts import build_chat_messages
from app.agent.results import parse_structured_result
from app.agent.schemas import AgentChatRequest, AgentChatData, AgentContext, AgentRouteInfo, ToolName
from app.agent.tools import get_agent_tool
from config.settings import settings


class StreamEventType(Enum):
    START = "start"
    CONTENT = "content"
    ROUTE = "route"
    KNOWLEDGE = "knowledge"
    FINISH = "finish"
    ERROR = "error"


@dataclass
class StreamEvent:
    type: StreamEventType
    data: Optional[dict] = None
    content: Optional[str] = None


async def chat_stream(
    service,
    payload: AgentChatRequest,
) -> AsyncGenerator[StreamEvent, None]:
    user_message = service.extract_user_message(payload)

    try:
        yield StreamEvent(type=StreamEventType.START)

        route = await service.router.resolve(user_message)
        yield StreamEvent(
            type=StreamEventType.ROUTE,
            data={
                "tool_name": route.tool_name,
                "confidence": route.confidence,
                "reason": route.reason,
                "strategy": route.strategy.value,
                "matched_keyword": route.matched_keyword,
            },
        )

        knowledge_block = await service._retrieve_knowledge(
            query=user_message,
            current_lesson=payload.context.current_lesson if payload.context else None,
        )
        if knowledge_block:
            yield StreamEvent(type=StreamEventType.KNOWLEDGE, data={"content": knowledge_block})

        messages = build_chat_messages(
            user_message=user_message,
            history=payload.history,
            context=payload.context,
            max_turns=settings.OPENAI_MAX_TURNS,
            tool_name=route.tool_name,
        )
        messages = service._inject_knowledge(messages, knowledge_block)

        full_content = ""
        api_key = settings.effective_llm_api_key
        base_url = settings.effective_llm_base_url

        if api_key and base_url:
            try:
                client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                stream = await client.chat.completions.create(
                    model=service.model,
                    messages=messages,
                    temperature=0.3,
                    stream=True,
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_content += content
                        yield StreamEvent(type=StreamEventType.CONTENT, content=content)
            except Exception:
                full_content = get_agent_tool(route.tool_name).fallback_content
                yield StreamEvent(type=StreamEventType.CONTENT, content=full_content)
        else:
            full_content = get_agent_tool(route.tool_name).fallback_content
            yield StreamEvent(type=StreamEventType.CONTENT, content=full_content)

        structured_result = parse_structured_result(route.tool_name, full_content)
        yield StreamEvent(
            type=StreamEventType.FINISH,
            data={
                "tool_name": route.tool_name,
                "model": service.model,
                "used_fallback": not (api_key and base_url),
                "structured_result": structured_result.model_dump() if structured_result else None,
            },
        )

    except Exception as e:
        yield StreamEvent(
            type=StreamEventType.ERROR,
            data={"message": str(e)},
        )


def format_sse(event: StreamEvent) -> str:
    lines = []
    lines.append(f"event: {event.type.value}")
    if event.content:
        lines.append(f"data: {event.content}")
    elif event.data:
        lines.append(f"data: {json.dumps(event.data, ensure_ascii=False)}")
    lines.append("\n")
    return "\n".join(lines)
