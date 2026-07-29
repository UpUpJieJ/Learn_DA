"""LLM 调用层适配器（阶段 ② Task 2.1）。

统一封装 chat.completions 调用：总超时、有限重试、错误分类、结构化日志。
上层（AgentService）只消费 LLMResult，不再直接接触 openai SDK 异常；
error_reason 会在阶段 ② Task 2.2 透出为响应的 fallback_reason。
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal

import openai

from app.utils import log
from app.utils.logger import request_id_var
from config.settings import settings

LLMErrorReason = Literal[
    "no_api_key",
    "auth_error",
    "rate_limited",
    "timeout",
    "upstream_error",
    "empty_response",
]

# 瞬态故障才值得重试；认证错误/空响应重试无意义
_RETRYABLE_REASONS: frozenset[str] = frozenset(
    {"timeout", "rate_limited", "upstream_error"}
)


@dataclass(frozen=True)
class LLMToolCall:
    """归一化的工具调用：arguments 保留原始 JSON 字符串，由执行器负责校验。"""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LLMResult:
    content: str | None
    error_reason: LLMErrorReason | None
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # Function Calling 返回的工具调用；非空时 content 可为 None 且不算空响应
    tool_calls: tuple["LLMToolCall", ...] = ()

    @property
    def ok(self) -> bool:
        return self.error_reason is None


class LLMClient:
    """基于注入的 AsyncOpenAI（或兼容对象）的调用适配器。

    client 为 None 表示未配置 API key，complete 直接返回 no_api_key，
    保证无 key 时的确定性降级路径不发任何网络请求。
    """

    def __init__(
        self,
        client: Any | None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        backoff_base_seconds: float = 0.5,
    ) -> None:
        self._client = client
        self.model = model or settings.effective_llm_model
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.LLM_TIMEOUT_SECONDS
        )
        self.max_retries = (
            max_retries if max_retries is not None else settings.LLM_MAX_RETRIES
        )
        self.backoff_base_seconds = backoff_base_seconds

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float = 0.3,
    ) -> LLMResult:
        started = time.monotonic()
        if self._client is None:
            return self._finish(started, None, "no_api_key", attempt=0)

        attempts = 1 + max(self.max_retries, 0)
        reason: LLMErrorReason = "upstream_error"
        for attempt in range(attempts):
            if attempt > 0 and self.backoff_base_seconds > 0:
                await asyncio.sleep(self.backoff_base_seconds * (2 ** (attempt - 1)))
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    response = await self._create(
                        messages, tools=tools, tool_choice=tool_choice,
                        temperature=temperature,
                    )
            except openai.AuthenticationError:
                return self._finish(started, None, "auth_error", attempt)
            except openai.RateLimitError:
                reason = "rate_limited"
                continue
            except (openai.APITimeoutError, TimeoutError):
                reason = "timeout"
                continue
            except Exception:
                reason = "upstream_error"
                continue

            content = self._extract_content(response)
            tool_calls = self._extract_tool_calls(response)
            usage = getattr(response, "usage", None)
            if content is None and not tool_calls:
                return self._finish(
                    started, None, "empty_response", attempt, usage=usage
                )
            return self._finish(
                started, content, None, attempt, usage=usage, tool_calls=tool_calls
            )

        # 可重试错误耗尽全部尝试次数
        return self._finish(started, None, reason, attempts - 1)

    async def _create(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        temperature: float,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        extra_body: dict[str, Any] = {}
        if settings.LLM_ENABLE_THINKING:
            extra_body["enable_thinking"] = True
        if extra_body:
            kwargs["extra_body"] = extra_body
        return await self._client.chat.completions.create(**kwargs)

    def _extract_content(self, response: Any) -> str | None:
        choices = getattr(response, "choices", None)
        if not choices:
            return None
        message = choices[0].message
        content = getattr(message, "content", None) if message else None
        # 空白内容视同空响应，上层拿到 content 即保证可用
        content = content.strip() if content else None
        return content or None

    def _extract_tool_calls(self, response: Any) -> tuple[LLMToolCall, ...]:
        choices = getattr(response, "choices", None)
        if not choices:
            return ()
        message = choices[0].message
        raw_calls = getattr(message, "tool_calls", None) if message else None
        if not raw_calls:
            return ()
        calls = []
        for raw in raw_calls:
            function = getattr(raw, "function", None)
            name = getattr(function, "name", None) if function else None
            if not name:
                continue
            calls.append(
                LLMToolCall(
                    id=getattr(raw, "id", "") or "",
                    name=name,
                    arguments=getattr(function, "arguments", None) or "{}",
                )
            )
        return tuple(calls)

    def _finish(
        self,
        started: float,
        content: str | None,
        error_reason: LLMErrorReason | None,
        attempt: int,
        usage: Any = None,
        tool_calls: tuple[LLMToolCall, ...] = (),
    ) -> LLMResult:
        latency_ms = int((time.monotonic() - started) * 1000)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        log.info(
            "[llm] request_id={} model={} latency_ms={} attempts={} "
            "prompt_tokens={} completion_tokens={} error_reason={}",
            request_id_var.get(),
            self.model,
            latency_ms,
            attempt + 1,
            prompt_tokens,
            completion_tokens,
            error_reason or "-",
        )
        return LLMResult(
            content=content,
            error_reason=error_reason,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tool_calls=tool_calls,
        )
