"""AI 助手（改版 E1）：提示层级进 prompt、工作区定位字段进上下文。

E1 之前 ``_resolve_hint_level`` 算出的层级只回给前端展示，模型完全不知道
自己该给第几层提示（``prompts.py`` 里没有任何 hint 字样），分级形同虚设。
这些测试锁住三件事：

* 层级被翻译成模型能执行的指令，并出现在最终发给模型的 messages 里；
* 层级指令插在提问之前，不破坏 system prompt 在首位；
* 工作区定位字段（sessionId / cellId / recentRuns）能进上下文块，且被
  明确标注为「客户端自报，判定以服务端证据为准」，不会被当成教学证据。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.evidence import AgentLearningEvidence
from app.agent.llm_client import LLMResult
from app.agent.prompts import (
    build_context_block,
    build_evidence_block,
    build_hint_directive,
)
from app.agent.schemas import AgentChatRequest, AgentContext, AgentRecentRun
from app.agent.service import AgentService

pytestmark = pytest.mark.anyio


# ---- 层级指令 ----


def test_hint_directive_is_empty_without_level():
    assert build_hint_directive(None) == ""
    assert build_hint_directive(0) == ""


@pytest.mark.parametrize(
    ("level", "marker"),
    [
        (1, "只指出方向"),
        (2, "不要写出完整语句"),
        (3, "一行可复制的关键写法"),
    ],
)
def test_hint_directive_encodes_depth(level: int, marker: str):
    line = build_hint_directive(level)

    assert f"L{level}" in line
    assert marker in line


def test_hint_directive_clamps_out_of_range_levels():
    assert build_hint_directive(9).startswith("本次提示层级：L3")
    assert build_hint_directive(-3).startswith("本次提示层级：L1")


def test_evidence_block_carries_hint_level():
    block = build_evidence_block(None, hint_level=2)

    assert "学习者暂无可用任务证据" in block
    assert "本次提示层级：L2" in block


# ---- 层级指令进 messages ----


def test_hint_directive_is_inserted_before_the_question():
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "为什么这条断言不过"},
    ]

    result = AgentService._with_hint_directive(messages, 2)

    assert result[0] == messages[0]
    assert result[1]["role"] == "system"
    assert "本次提示层级：L2" in result[1]["content"]
    assert result[-1] == messages[-1]


def test_hint_directive_leaves_messages_untouched_without_level():
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "问题"},
    ]

    assert AgentService._with_hint_directive(messages, None) is messages
    assert AgentService._with_hint_directive([], 2) == []


# ---- 工作区定位字段 ----


def test_context_block_marks_recent_runs_as_client_reported():
    context = AgentContext.model_validate(
        {
            "currentLesson": "polars-groupby",
            "currentTask": "t2",
            "sessionId": 41,
            "cellId": "c2",
            "recentRuns": [
                {
                    "cellId": "c2",
                    "status": "error",
                    "errorType": "ColumnNotFoundError",
                    "stderrFirstLine": "unable to find column total",
                },
                {
                    "cellId": "c3",
                    "status": "success",
                    "assertionsFailed": ["t2-share"],
                },
            ],
        }
    )

    block = build_context_block(context)

    assert "工作区会话：41" in block
    assert "当前聚焦的单元格：c2" in block
    assert "客户端自报，仅用于定位，判定以服务端证据为准" in block
    assert "c2：error，ColumnNotFoundError —— unable to find column total" in block
    assert "c3：success（未通过断言：t2-share）" in block


def test_context_block_omits_workspace_lines_when_absent():
    block = build_context_block(AgentContext.model_validate({"currentLesson": "x"}))

    assert "工作区会话" not in block
    assert "当前聚焦的单元格" not in block
    assert "最近的单元格执行" not in block


def test_recent_runs_are_capped_at_three():
    with pytest.raises(ValueError):
        AgentContext.model_validate(
            {
                "recentRuns": [
                    {"cellId": f"c{index}", "status": "success"} for index in range(4)
                ]
            }
        )


def test_recent_runs_accept_camel_case_payload():
    request = AgentChatRequest.model_validate(
        {
            "message": "刚才那个报错",
            "context": {
                "currentLesson": "polars-groupby",
                "sessionId": 7,
                "recentRuns": [
                    {
                        "cellId": "c1",
                        "status": "error",
                        "errorType": "NameError",
                        "stderrFirstLine": "name 'region_share' is not defined",
                        "assertionsFailed": [],
                    }
                ],
            },
        }
    )

    runs = request.context.recent_runs
    assert len(runs) == 1
    assert runs[0].error_type == "NameError"
    # 序列化必须仍是 camelCase，前端只认这套字段
    assert json.loads(runs[0].model_dump_json(by_alias=True))["errorType"] == "NameError"


def test_recent_run_stderr_is_truncated_by_schema():
    with pytest.raises(ValueError):
        AgentRecentRun.model_validate({"stderrFirstLine": "x" * 401})


# ---- 端到端：层级真的进了发给模型的 messages ----


class _Recorder:
    """记录每次 LLM 调用的 messages，并返回固定回答。"""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def __call__(self, messages, tools=None, tool_choice=None):
        self.calls.append([dict(message) for message in messages])
        return LLMResult(content="回答", error_reason=None, latency_ms=1)


def _service_with_evidence(completer: _Recorder, helps: int) -> AgentService:
    """构造一个能算出 hint_level 的服务：证据带课程 slug，求助计数由 repo 给。"""

    evidence = AgentLearningEvidence(
        state="verification_failed", lesson_slug="polars-groupby", attempt_id=9
    )
    interaction = MagicMock()
    interaction.id = 1
    interaction.visitor_id = "v1"
    interaction.request_id = "req-assistant"

    repo = MagicMock()
    repo.get_or_create = AsyncMock(return_value=(interaction, True))
    repo.fill_metrics = AsyncMock()
    repo.count_by_visitor_and_lesson = AsyncMock(return_value=helps)

    service = AgentService(interaction_repo=repo)
    service._inject_evidence = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            [
                {"role": "system", "content": "你是助手"},
                {"role": "user", "content": "这条断言为什么不通过"},
            ],
            evidence,
        )
    )
    service._complete = completer  # type: ignore[method-assign]
    return service


@pytest.mark.parametrize(
    ("helps", "level"),
    [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (9, 3)],
)
async def test_hint_level_reaches_the_model_prompt(helps: int, level: int):
    completer = _Recorder()
    service = _service_with_evidence(completer, helps)

    await service.chat_with_tools(
        AgentChatRequest(message="这条断言为什么不通过"), visitor_id="v1"
    )

    sent = completer.calls[0]
    directive = [
        message["content"]
        for message in sent
        if message["role"] == "system" and "本次提示层级" in message["content"]
    ]
    assert directive, f"层级指令没有进入 messages：{[m['role'] for m in sent]}"
    assert f"L{level}" in directive[0]
    # system prompt 仍在首位，层级指令插在提问之前
    assert sent[0]["content"] == "你是助手"
    assert sent[-1]["role"] == "user"
    assert "本次提示层级" in sent[-2]["content"]

