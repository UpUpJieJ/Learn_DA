"""评测数据集 schema 校验（阶段 ③ Task 3.2）。

保证 tests/eval/ 下两个用例文件结构合法：
- 意图用例：expected_intent 落在 ToolName 六值域内，条数 30-50；
- 检索用例：expected_lesson_slug 是真实存在的课程 slug，条数 15-20。
数据文件损坏时评测 runner 的基线数字不可信，因此纳入单测门禁。
"""

from pathlib import Path
from typing import get_args

import yaml

from app.agent.schemas import ToolName
from app.core.content_loader import load_all_lessons

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
INTENT_FILE = EVAL_DIR / "agent_intent_cases.yml"
RETRIEVAL_FILE = EVAL_DIR / "agent_retrieval_cases.yml"

VALID_INTENTS = set(get_args(ToolName))


def load_cases(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name} 顶层必须是 mapping"
    cases = data.get("cases")
    assert isinstance(cases, list) and cases, f"{path.name} 必须包含非空 cases 列表"
    return cases


def test_intent_cases_schema():
    cases = load_cases(INTENT_FILE)
    assert 30 <= len(cases) <= 50, f"意图用例应为 30-50 条，实际 {len(cases)}"
    for index, case in enumerate(cases):
        assert isinstance(case.get("message"), str) and case["message"].strip(), (
            f"第 {index} 条 message 必须为非空字符串"
        )
        assert case.get("expected_intent") in VALID_INTENTS, (
            f"第 {index} 条 expected_intent={case.get('expected_intent')!r} "
            f"不在 ToolName 值域内"
        )
        tags = case.get("tags")
        assert isinstance(tags, list) and tags, f"第 {index} 条 tags 必须为非空列表"
        assert all(isinstance(tag, str) and tag for tag in tags)


def test_intent_cases_messages_unique():
    cases = load_cases(INTENT_FILE)
    messages = [case["message"] for case in cases]
    assert len(messages) == len(set(messages)), "意图用例 message 不允许重复"


def test_intent_cases_cover_all_intents():
    cases = load_cases(INTENT_FILE)
    covered = {case["expected_intent"] for case in cases}
    assert covered == VALID_INTENTS, f"缺少意图覆盖：{VALID_INTENTS - covered}"


def test_retrieval_cases_schema():
    cases = load_cases(RETRIEVAL_FILE)
    assert 15 <= len(cases) <= 20, f"检索用例应为 15-20 条，实际 {len(cases)}"
    valid_slugs = {lesson.get("slug") for lesson in load_all_lessons()}
    for index, case in enumerate(cases):
        assert isinstance(case.get("query"), str) and case["query"].strip(), (
            f"第 {index} 条 query 必须为非空字符串"
        )
        assert case.get("expected_lesson_slug") in valid_slugs, (
            f"第 {index} 条 expected_lesson_slug="
            f"{case.get('expected_lesson_slug')!r} 不是真实课程 slug"
        )
        tags = case.get("tags")
        assert isinstance(tags, list) and tags, f"第 {index} 条 tags 必须为非空列表"


def test_retrieval_cases_queries_unique():
    cases = load_cases(RETRIEVAL_FILE)
    queries = [case["query"] for case in cases]
    assert len(queries) == len(set(queries)), "检索用例 query 不允许重复"
