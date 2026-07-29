"""Task 2.1: LLMClient 适配器 — 超时、有限重试、错误分类。

不发真实请求：用 fake client 模拟各类 openai 异常，
断言错误分类正确、重试策略符合约定（auth 不重试、429/超时/上游错误重试）。
"""

import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.agent.llm_client import LLMClient, LLMResult

pytestmark = pytest.mark.unit


def _http_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "http://llm.test/v1/chat/completions")
    return httpx.Response(status_code, request=request)


def _auth_error() -> openai.AuthenticationError:
    return openai.AuthenticationError(
        "invalid key", response=_http_response(401), body=None
    )


def _rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError(
        "rate limited", response=_http_response(429), body=None
    )


def _timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(
        request=httpx.Request("POST", "http://llm.test/v1/chat/completions")
    )


def _success_response(content: str = "ok") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


class FakeRawClient:
    """模拟 AsyncOpenAI：按 outcomes 顺序逐次抛异常或返回响应。"""

    def __init__(self, outcomes: list) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_llm_client(raw, **overrides) -> LLMClient:
    params = {
        "client": raw,
        "model": "test-model",
        "timeout_seconds": 5.0,
        "max_retries": 1,
        "backoff_base_seconds": 0.0,
    }
    params.update(overrides)
    return LLMClient(**params)


MESSAGES = [{"role": "user", "content": "hi"}]


async def test_no_client_returns_no_api_key():
    llm = make_llm_client(None)
    result = await llm.complete(MESSAGES)
    assert isinstance(result, LLMResult)
    assert result.content is None
    assert result.error_reason == "no_api_key"


async def test_success_returns_content_and_tokens():
    raw = FakeRawClient([_success_response("hello")])
    result = await make_llm_client(raw).complete(MESSAGES)
    assert result.content == "hello"
    assert result.error_reason is None
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 7
    assert result.latency_ms >= 0
    assert len(raw.calls) == 1


async def test_auth_error_not_retried():
    raw = FakeRawClient([_auth_error(), _success_response()])
    result = await make_llm_client(raw).complete(MESSAGES)
    assert result.error_reason == "auth_error"
    assert len(raw.calls) == 1  # 认证错误重试无意义


async def test_rate_limit_retried_then_succeeds():
    raw = FakeRawClient([_rate_limit_error(), _success_response("second")])
    result = await make_llm_client(raw).complete(MESSAGES)
    assert result.content == "second"
    assert result.error_reason is None
    assert len(raw.calls) == 2


async def test_rate_limit_exhausts_retries():
    raw = FakeRawClient([_rate_limit_error(), _rate_limit_error()])
    result = await make_llm_client(raw).complete(MESSAGES)
    assert result.error_reason == "rate_limited"
    assert len(raw.calls) == 2  # 1 次原始 + max_retries=1 次重试


async def test_api_timeout_classified_and_retried():
    raw = FakeRawClient([_timeout_error(), _timeout_error()])
    result = await make_llm_client(raw).complete(MESSAGES)
    assert result.error_reason == "timeout"
    assert len(raw.calls) == 2


async def test_generic_error_classified_upstream():
    raw = FakeRawClient([RuntimeError("boom"), RuntimeError("boom")])
    result = await make_llm_client(raw).complete(MESSAGES)
    assert result.error_reason == "upstream_error"
    assert len(raw.calls) == 2


async def test_empty_choices_is_empty_response_no_retry():
    raw = FakeRawClient(
        [SimpleNamespace(choices=[], usage=None), _success_response()]
    )
    result = await make_llm_client(raw).complete(MESSAGES)
    assert result.error_reason == "empty_response"
    assert len(raw.calls) == 1  # 空响应不是瞬态故障，不重试


async def test_overall_timeout_enforced():
    async def slow_create(**kwargs):
        await asyncio.sleep(1.0)

    raw = FakeRawClient([])
    raw.chat = SimpleNamespace(completions=SimpleNamespace(create=slow_create))
    llm = make_llm_client(raw, timeout_seconds=0.05, max_retries=0)
    result = await llm.complete(MESSAGES)
    assert result.error_reason == "timeout"


async def test_tools_passed_through_to_create():
    raw = FakeRawClient([_success_response()])
    tools = [{"type": "function", "function": {"name": "search_knowledge"}}]
    await make_llm_client(raw).complete(
        MESSAGES, tools=tools, tool_choice="auto"
    )
    assert raw.calls[0]["tools"] == tools
    assert raw.calls[0]["tool_choice"] == "auto"


async def test_settings_defaults_exist():
    from config.settings import settings

    assert settings.LLM_TIMEOUT_SECONDS > 0
    assert settings.LLM_MAX_RETRIES >= 0
