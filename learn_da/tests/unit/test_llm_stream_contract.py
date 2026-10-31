import asyncio
from types import SimpleNamespace as NS

import pytest

from app.agent.llm_client import LLMClient


def chunk(text=None, finish=None, calls=None):
    return NS(choices=[NS(delta=NS(content=text, tool_calls=calls), finish_reason=finish)])


class Raw:
    def __init__(self, chunks, delay=0):
        self.chunks = chunks
        self.delay = delay
        self.closed = False
        self.chat = NS(completions=NS(create=self.create))

    async def create(self, **kwargs):
        async def stream():
            try:
                for item in self.chunks:
                    await asyncio.sleep(self.delay)
                    yield item
            finally:
                self.closed = True
        return stream()


def client(raw, timeout=1):
    return LLMClient(client=raw, model="test", timeout_seconds=timeout, max_retries=0)


async def test_repeated_tool_name_is_not_concatenated():
    call = lambda args: NS(index=0, id="call1", function=NS(name="search_knowledge", arguments=args))
    raw = Raw([chunk(calls=[call('{"query":')]), chunk(calls=[call('"x"}')]), chunk(finish="tool_calls")])
    events = [event async for event in client(raw).stream([])]
    assert events[-1].tool_calls[0].name == "search_knowledge"
    assert events[-1].tool_calls[0].arguments == '{"query":"x"}'


@pytest.mark.parametrize("finish", ["length", "content_filter", None])
async def test_incomplete_finish_is_reported_as_interruption(finish):
    raw = Raw([chunk("partial"), chunk(finish=finish)])
    events = [event async for event in client(raw).stream([])]
    assert events[-1].interrupted
    assert events[-1].error_reason == "truncated"


async def test_timeout_is_idle_timeout_not_total_stream_duration():
    raw = Raw([chunk("a"), chunk("b"), chunk(finish="stop")], delay=0.03)
    events = [event async for event in client(raw, timeout=0.07).stream([])]
    assert events[-1].error_reason is None
    assert "".join(e.delta for e in events) == "ab"
    assert raw.closed


async def test_stalled_stream_is_closed_on_timeout():
    raw = Raw([chunk("a")], delay=0.1)
    events = [event async for event in client(raw, timeout=0.01).stream([])]
    assert events[-1].error_reason == "timeout"
    assert raw.closed


async def test_continuous_deltas_are_bounded_by_total_budget():
    raw = Raw([chunk("x") for _ in range(100)], delay=0.01)
    llm = LLMClient(client=raw, model="test", timeout_seconds=1,
                    stream_total_timeout_seconds=0.05, max_retries=2)
    events = [event async for event in llm.stream([])]
    assert events[-1].error_reason == "timeout"
    assert events[-1].interrupted
    assert 0 < len([e for e in events if e.delta]) < 100
    assert raw.closed
