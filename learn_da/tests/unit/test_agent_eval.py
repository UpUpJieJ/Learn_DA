"""阶段 3 Task 5：学习证据驱动 Agent 离线评测（改版 M4 起为工作区语义）。

加载 ``tests/eval/phase3_evidence_cases.yml``，对每条 case 用
``AgentEvidenceResolver`` + ``build_teaching_feedback`` + ``derive_next_action``
做确定性断言（不调用 LLM），覆盖 6 个评测维度：

1. evidence_accuracy   证据五态推导（由 Runner verdict + 教学状态推导）
2. next_action          下一步动作映射
3. hint_escalation     分级提示逐级升高
4. code_leak           证据/反馈不泄露历史提交的完整代码
5. fallback_class      fallback 原因分类
6. runner_unavailable   Runner 不可用 / 断言未求值不进入 execution_failed

case 里的 ``verdict`` / ``status`` 与 ``task_attempts`` 落库的字段一致；
``verdict`` / ``status`` 同时为 null 表示该学习者还没有任何提交。
"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from app.agent.evidence import (
    AgentEvidenceResolver,
    build_teaching_feedback,
    derive_next_action,
)

EVAL_YML = Path(__file__).parent.parent / "eval" / "phase3_evidence_cases.yml"
LESSON = "polars-groupby"
LESSON_TASKS = ("t1", "t2")


def _load_cases() -> list[dict]:
    with open(EVAL_YML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["cases"]


CASES = _load_cases()


def _make_attempt(case: dict) -> SimpleNamespace | None:
    """从 case 构造内存 TaskAttempt 替身（verdict/status 都为 null 表示无提交）。"""
    if case["verdict"] is None and case["status"] is None:
        return None
    return SimpleNamespace(
        id=case.get("attempt_id", 1),
        visitor_id="visitor-A",
        lesson_slug=LESSON,
        task_id="t1",
        attempt_no=1,
        status=case["status"],
        verdict=case["verdict"],
        # 证据链禁止泄露完整代码，这里放一个哨兵值用于断言
        code="SECRET_CODE_THAT_MUST_NOT_LEAK",
        actual="表达式为假",
        assertions="[]",
        created_time=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )


def _make_repo(attempt: SimpleNamespace | None, lesson_completed: bool) -> MagicMock:
    repo = MagicMock()
    repo.get_attempt = AsyncMock(return_value=attempt)
    repo.latest_attempt = AsyncMock(return_value=attempt)
    passed = set(LESSON_TASKS) if lesson_completed else set()
    repo.lesson_task_stats = AsyncMock(return_value=(passed, len(LESSON_TASKS)))
    return repo


def _make_resolver(
    attempt: SimpleNamespace | None, lesson_completed: bool
) -> AgentEvidenceResolver:
    return AgentEvidenceResolver(workspace_repo=_make_repo(attempt, lesson_completed))


def _hint_level_from_turns(turns: int) -> int:
    """与 AgentService._estimate_hint_level 对齐的近似。"""
    return max(1, min(3, 1 + turns // 2))


# =====================================================
# 参数化离线评测：每条 case 一组断言
# =====================================================


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
@pytest.mark.asyncio
async def test_phase3_eval_case(case: dict):
    """对单条 eval case 做证据推导 + 反馈契约断言。"""
    attempt = _make_attempt(case)
    resolver = _make_resolver(attempt, case["lesson_completed"])

    evidence = await resolver.resolve(
        visitor_id="visitor-A",
        lesson_slug=LESSON,
        attempt_id=case.get("attempt_id", 1),
    )

    # 维度 1：证据五态推导
    assert evidence.state == case["expected_state"], (
        f"{case['id']}: state={evidence.state} expected={case['expected_state']}"
    )

    # 维度 2：下一步动作映射
    assert derive_next_action(evidence) == case["expected_next_action"]

    # 维度 3：分级提示
    hint_level = _hint_level_from_turns(case["history_user_turns"])
    fb = build_teaching_feedback(evidence, hint_level=hint_level)
    assert fb.hint_level == case["expected_hint_level"]
    assert fb.next_action == case["expected_next_action"]
    assert fb.state == case["expected_state"]

    # 维度 4：代码泄露——证据与反馈序列化中不含 code / 完整代码
    ev_dumped = evidence.model_dump()
    assert "code" not in ev_dumped
    assert "SECRET_CODE" not in str(ev_dumped)
    fb_dumped = fb.model_dump(by_alias=True)
    assert "code" not in fb_dumped
    assert "SECRET_CODE" not in str(fb_dumped)


# =====================================================
# 维度 6：游客隔离（伪造 attemptId 得不到他人证据）
# =====================================================


class TestVisitorIsolation:
    @pytest.mark.asyncio
    async def test_forged_attempt_id_no_evidence(self):
        """攻击者用他人的 attemptId 查不到证据。"""
        repo = MagicMock()
        # get_attempt 按 visitor 过滤，攻击者查不到 victim 的提交
        repo.get_attempt = AsyncMock(return_value=None)
        repo.latest_attempt = AsyncMock(return_value=None)
        repo.lesson_task_stats = AsyncMock(return_value=(set(), len(LESSON_TASKS)))

        resolver = AgentEvidenceResolver(workspace_repo=repo)
        evidence = await resolver.resolve(
            visitor_id="attacker",
            lesson_slug=LESSON,
            attempt_id=999,
        )
        assert evidence.state == "no_evidence"
        # 校验用了攻击者身份（参数顺序：visitor_id, attempt_id）
        repo.get_attempt.assert_called_once_with("attacker", 999)

    @pytest.mark.asyncio
    async def test_victim_evidence_not_leaked_to_attacker(self):
        """victim 的提交存在，但攻击者查不到。"""
        repo = MagicMock()
        # 攻击者查 attempt_id=42 -> None（visitor 不匹配）
        repo.get_attempt = AsyncMock(return_value=None)
        repo.latest_attempt = AsyncMock(return_value=None)
        repo.lesson_task_stats = AsyncMock(return_value=(set(), len(LESSON_TASKS)))

        resolver = AgentEvidenceResolver(workspace_repo=repo)
        evidence = await resolver.resolve(
            visitor_id="attacker",
            lesson_slug=LESSON,
            attempt_id=42,
        )
        assert evidence.state == "no_evidence"
        assert evidence.attempt_id is None


# =====================================================
# 维度 4 独立：代码泄露专项
# =====================================================


class TestCodeLeakage:
    @pytest.mark.asyncio
    async def test_evidence_never_contains_code(self):
        """无论何种 verdict/status，证据都不含 code 字段。"""
        for verdict, status in [
            ("execution_failed", "failed"),
            ("assertion_failed", "failed"),
            ("passed", "passed"),
            (None, "skipped"),
        ]:
            attempt = SimpleNamespace(
                id=1,
                visitor_id="v1",
                lesson_slug=LESSON,
                task_id="t1",
                attempt_no=1,
                status=status,
                verdict=verdict,
                code=f"SECRET_{status}",
                actual="表达式为假",
                assertions="[]",
                created_time=datetime(2026, 7, 31, tzinfo=timezone.utc),
            )
            repo = MagicMock()
            repo.get_attempt = AsyncMock(return_value=attempt)
            repo.latest_attempt = AsyncMock(return_value=attempt)
            repo.lesson_task_stats = AsyncMock(
                return_value=(set(), len(LESSON_TASKS))
            )

            resolver = AgentEvidenceResolver(workspace_repo=repo)
            evidence = await resolver.resolve("v1", LESSON, 1)
            dumped = str(evidence.model_dump())
            assert "code" not in evidence.model_dump()
            assert f"SECRET_{status}" not in dumped


# =====================================================
# 评测集完整性汇总
# =====================================================


def test_eval_summary(capsys: pytest.CaptureFixture[str]):
    """确保评测集覆盖声明的维度，不伪造未执行的通过率。"""
    dim_total: dict[str, int] = {}
    required_dimensions = {
        "evidence_accuracy",
        "next_action",
        "hint_escalation",
        "code_leak",
        "fallback_class",
        "runner_unavailable",
    }
    for case in CASES:
        dim = case["dimension"]
        dim_total[dim] = dim_total.get(dim, 0) + 1

    assert required_dimensions.issubset(dim_total)
    assert len(CASES) >= 30

    lines = ["\n=== 阶段 3 离线评测汇总 ==="]
    for dim in sorted(dim_total):
        lines.append(f"  {dim}: {dim_total[dim]} 条 case，断言由参数化测试执行")
    lines.append("  visitor_isolation: 由独立归属隔离测试执行")
    lines.append(f"  总计: {len(CASES)} 条 case")
    print("\n".join(lines))
