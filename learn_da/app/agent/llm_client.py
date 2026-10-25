"""LLM 调用层适配器（阶段 ② Task 2.1，E3 起支持流式）。

统一封装 chat.completions 调用：总超时、有限重试、错误分类、结构化日志。
上层（AgentService）只消费 LLMResult / LLMStreamEvent，不再直接接触 openai
SDK 异常；error_reason 会透出为响应的 fallback_reason。

流式（``stream``）与一次性（``complete``）共用同一套错误分类与重试策略，
唯一区别是**已经吐出过 token 之后不能再重试**：重试会让学习者看到重复的
开头，所以中途失败只能如实报告，由上层把已生成的部分和中断原因一起交付。
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

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


@dataclass(frozen=True)
class LLMStreamEvent:
    """流式过程中的单个事件。

    ``delta`` 非空表示这是一段可以直接渲染给学习者的文本；
    ``done=True`` 表示本轮结束，此时才带 ``error_reason`` / usage / tool_calls。
    上层不需要拼接 content，自己累积 delta 即可。
    """

    delta: str = ""
    done: bool = False
    error_reason: LLMErrorReason | None = None
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tool_calls: tuple[LLMToolCall, ...] = ()
    # 是否在吐出过内容之后中断（此时不能重试，也不能当成完整回答）
    interrupted: bool = False


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
        self.model = model or settings.LLM_MODEL
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

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float = 0.3,
    ) -> AsyncIterator[LLMStreamEvent]:
        """流式调用：边收边吐 delta，最后一个事件的 ``done=True``。

        与 ``complete`` 的差别只有两点：
        1. 文本以增量形式产出，上层不必等整段；
        2. **已吐字之后不再重试**（重试会让学习者看到重复开头），
           中途失败以 ``interrupted=True`` 如实结束。
        """
        started = time.monotonic()
        if self._client is None:
            yield self._stream_done(started, "no_api_key")
            return

        attempts = 1 + max(self.max_retries, 0)
        reason: LLMErrorReason = "upstream_error"
        for attempt in range(attempts):
            if attempt > 0 and self.backoff_base_seconds > 0:
                await asyncio.sleep(self.backoff_base_seconds * (2 ** (attempt - 1)))
            emitted = False
            text_parts: list[str] = []
            tool_calls: dict[int, dict[str, str]] = {}
            usage: Any = None
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    stream = await self._create_stream(
                        messages,
                        tools=tools,
                        tool_choice=tool_choice,
                        temperature=temperature,
                    )
                    async for chunk in stream:
                        if getattr(chunk, "usage", None):
                            usage = chunk.usage
                        choices = getattr(chunk, "choices", None) or []
                        if not choices:
                            continue
                        delta = choices[0].delta
                        piece = getattr(delta, "content", None)
                        if piece:
                            text_parts.append(piece)
                            emitted = True
                            yield LLMStreamEvent(delta=piece)
                        self._accumulate_tool_calls(
                            tool_calls, getattr(delta, "tool_calls", None)
                        )
            except openai.AuthenticationError:
                yield self._stream_done(started, "auth_error", interrupted=emitted)
                return
            except (openai.RateLimitError, openai.APITimeoutError, TimeoutError) as exc:
                reason = (
                    "timeout"
                    if isinstance(exc, (openai.APITimeoutError, TimeoutError))
                    else "rate_limited"
                )
                if emitted:
                    # 已经吐过字：重试只会让开头重复，如实中断
                    yield self._stream_done(
                        started,
                        reason,
                        usage=usage,
                        interrupted=True,
                        partial="".join(text_parts),
                    )
                    return
                continue
            except Exception:
                reason = "upstream_error"
                if emitted:
                    yield self._stream_done(
                        started,
                        reason,
                        usage=usage,
                        interrupted=True,
                        partial="".join(text_parts),
                    )
                    return
                continue

            content = "".join(text_parts).strip()
            calls = self._tool_calls_tuple(tool_calls)
            if not content and not calls:
                # 空响应：与 complete 一致视为错误；没吐过字所以还能重试
                reason = "empty_response"
                if attempt + 1 < attempts:
                    continue
                yield self._stream_done(started, "empty_response", usage=usage)
                return
            yield self._stream_done(
                started, None, usage=usage, tool_calls=calls
            )
            return

        yield self._stream_done(started, reason)

    async def _create_stream(
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
            "stream": True,
            # 让 provider 在最后一个 chunk 回 usage，否则流式拿不到 token 数
            "stream_options": {"include_usage": True},
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

    @staticmethod
    def _accumulate_tool_calls(
        acc: dict[int, dict[str, str]],
        raw_calls: Any,
    ) -> None:
        """流式 tool_calls 是按 index 分片下发的，逐片累加 name/arguments。"""
        for raw in raw_calls or ():
            index = getattr(raw, "index", 0) or 0
            slot = acc.setdefault(index, {"id": "", "name": "", "arguments": ""})
            call_id = getattr(raw, "id", None)
            if call_id:
                slot["id"] = call_id
            function = getattr(raw, "function", None)
            if function is None:
                continue
            name = getattr(function, "name", None)
            if name:
                slot["name"] += name
            arguments = getattr(function, "arguments", None)
            if arguments:
                slot["arguments"] += arguments

    @staticmethod
    def _tool_calls_tuple(
        acc: dict[int, dict[str, str]],
    ) -> tuple[LLMToolCall, ...]:
        return tuple(
            LLMToolCall(
                id=slot["id"] or "",
                name=slot["name"],
                arguments=slot["arguments"] or "{}",
            )
            for _, slot in sorted(acc.items())
            if slot["name"]
        )

    def _stream_done(
        self,
        started: float,
        error_reason: LLMErrorReason | None,
        usage: Any = None,
        tool_calls: tuple[LLMToolCall, ...] = (),
        *,
        interrupted: bool = False,
        partial: str = "",
    ) -> LLMStreamEvent:
        latency_ms = int((time.monotonic() - started) * 1000)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        log.info(
            "[llm] stream request_id={} model={} latency_ms={} "
            "prompt_tokens={} completion_tokens={} error_reason={} interrupted={} "
            "partial_chars={}",
            request_id_var.get(),
            self.model,
            latency_ms,
            prompt_tokens,
            completion_tokens,
            error_reason or "-",
            interrupted,
            len(partial),
        )
        return LLMStreamEvent(
            done=True,
            error_reason=error_reason,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tool_calls=tool_calls,
            interrupted=interrupted,
        )

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
