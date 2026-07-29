"""Agent 离线评测 runner（阶段 ③ Task 3.2）。

对 tests/eval/ 下的两个数据集离线评测当前实现：
- 意图路由：逐条调用 ``AgentRouter.resolve()``，统计准确率与分 tag 明细；
- 知识检索：逐条调用 ``KnowledgeRetriever._keyword_search()``（强制关闭
  embedding 配置，不发任何网络请求），统计 hit@3 与分 tag 明细。

结果为确定性输出，可重复运行；基线数字记录在
``docs/agent-eval-baseline-2026-07.md``，作为阶段 ④ FC 改造的对比锚点。

用法::

    python scripts/eval_agent.py              # 输出意图 + 检索两份报告
    python scripts/eval_agent.py --verbose    # 额外列出每条错误用例

可选（需网络与 embedding 配置，手动步骤，不纳入基线）::

    python scripts/eval_agent.py --with-embedding

阶段 ④ FC 版意图评测（需真实 LLM key，产生 API 计费，手动步骤）::

    python scripts/eval_agent.py --fc

FC 形态下意图理解由模型承担（不再有关键词路由），故 FC 版意图评测
用强制 function calling 做六选一分类，与关键词基线同数据集同口径对比；
检索层 FC 与旧路径共用同一 ``KnowledgeRetriever.search``，不劣化由构造保证。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.knowledge import EmbeddingConfig, KnowledgeRetriever  # noqa: E402
from app.agent.routing import AgentRouter  # noqa: E402

EVAL_DIR = ROOT / "tests" / "eval"
TOP_K = 3


def load_cases(filename: str) -> list[dict]:
    data = yaml.safe_load((EVAL_DIR / filename).read_text(encoding="utf-8"))
    return data["cases"]


def evaluate_intent(verbose: bool) -> None:
    cases = load_cases("agent_intent_cases.yml")
    router = AgentRouter()

    total_hits = 0
    tag_stats: dict[str, list[int]] = defaultdict(
        lambda: [0, 0])  # tag -> [hit, total]
    failures: list[tuple[str, str, str]] = []

    for case in cases:
        route = router.resolve(case["message"])
        hit = route.tool_name == case["expected_intent"]
        total_hits += hit
        for tag in case["tags"]:
            tag_stats[tag][0] += hit
            tag_stats[tag][1] += 1
        if not hit:
            failures.append(
                (case["message"], case["expected_intent"], route.tool_name))

    print("=" * 60)
    print(f"意图路由（AgentRouter.resolve，共 {len(cases)} 条）")
    print(f"  准确率: {total_hits}/{len(cases)} = {total_hits / len(cases):.1%}")
    print("  分 tag 明细:")
    for tag, (hit, total) in sorted(tag_stats.items()):
        print(f"    {tag:<15} {hit}/{total} = {hit / total:.1%}")
    if verbose and failures:
        print("  错误用例（message | 期望 -> 实际）:")
        for message, expected, actual in failures:
            print(f"    {message} | {expected} -> {actual}")


def evaluate_retrieval(verbose: bool, with_embedding: bool) -> None:
    cases = load_cases("agent_retrieval_cases.yml")
    if with_embedding:
        # 手动对比步骤：走 settings 里的 embedding 配置，需要网络
        retriever = KnowledgeRetriever()
        mode = "embedding" if retriever.embedding_config.enabled else "keyword"

        async def search(query: str) -> list:
            return await retriever.search(query, limit=TOP_K)
    else:
        # 基线：显式禁用 embedding，纯离线关键词检索
        retriever = KnowledgeRetriever(
            embedding_config=EmbeddingConfig(
                api_key=None, base_url=None, model=None)
        )
        mode = "keyword"

        async def search(query: str) -> list:
            return retriever._keyword_search(query, current_lesson=None, limit=TOP_K)

    total_hits = 0
    tag_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    failures: list[tuple[str, str, list[str]]] = []

    async def run_all() -> list[list]:
        # 单一事件循环内跑完全部用例，embedding 模式下 client 与 loop 绑定才安全
        return [await search(case["query"]) for case in cases]

    for case, results in zip(cases, asyncio.run(run_all())):
        got_slugs = [chunk.lesson_slug for chunk in results]
        hit = case["expected_lesson_slug"] in got_slugs
        total_hits += hit
        for tag in case["tags"]:
            tag_stats[tag][0] += hit
            tag_stats[tag][1] += 1
        if not hit:
            failures.append(
                (case["query"], case["expected_lesson_slug"], got_slugs))

    print("=" * 60)
    print(f"知识检索（{mode}，hit@{TOP_K}，共 {len(cases)} 条）")
    print(
        f"  hit@{TOP_K}: {total_hits}/{len(cases)} = {total_hits / len(cases):.1%}")
    print("  分 tag 明细:")
    for tag, (hit, total) in sorted(tag_stats.items()):
        print(f"    {tag:<15} {hit}/{total} = {hit / total:.1%}")
    if verbose and failures:
        print("  未命中用例（query | 期望 slug | 实际前 3）:")
        for query, expected, got in failures:
            print(f"    {query} | {expected} | {got or '(零召回)'}")


# ---- FC 版意图评测（阶段 ④ Task 4.2 Step 2，需真实 LLM key）----

_INTENT_LABELS = (
    "generate_example_code",
    "generate_exercise",
    "fix_code",
    "explain_code",
    "suggest_next_step",
    "general_chat",
)

_CLASSIFY_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_intent",
        "description": "将用户消息归类到唯一最符合的意图",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": list(_INTENT_LABELS)}
            },
            "required": ["intent"],
        },
    },
}

_CLASSIFY_SYSTEM = (
    "你是数据分析学习平台（Polars/DuckDB/Python 课程 + 代码 Playground）的意图分类器。"
    "把用户消息归类到唯一最符合的意图："
    "generate_example_code=想要示例代码；generate_exercise=想要练习题；"
    "fix_code=代码报错/结果不对求修复；explain_code=解释代码/报错/概念含义；"
    "suggest_next_step=问学什么/学习路径建议；general_chat=闲聊或其他。"
    "必须调用 classify_intent 工具给出结果。"
)


async def evaluate_intent_fc(verbose: bool, concurrency: int = 4) -> None:
    """FC 版意图评测：强制 function calling 六选一分类，与关键词基线同口径。"""
    from openai import AsyncOpenAI

    from app.agent.llm_client import LLMClient
    from config.settings import settings

    api_key = settings.effective_llm_api_key
    if not api_key:
        print("=" * 60)
        print("FC 意图评测：未配置 LLM key，跳过")
        return

    cases = load_cases("agent_intent_cases.yml")
    client = AsyncOpenAI(
        api_key=api_key, base_url=settings.effective_llm_base_url)
    llm = LLMClient(client=client)
    semaphore = asyncio.Semaphore(concurrency)

    async def classify(message: str) -> str:
        async with semaphore:
            result = await llm.complete(
                [
                    {"role": "system", "content": _CLASSIFY_SYSTEM},
                    {"role": "user", "content": message},
                ],
                tools=[_CLASSIFY_TOOL],
                tool_choice={
                    "type": "function",
                    "function": {"name": "classify_intent"},
                },
                temperature=0.0,
            )
        if result.error_reason:
            return f"(error:{result.error_reason})"
        for call in result.tool_calls:
            if call.name != "classify_intent":
                continue
            try:
                intent = json.loads(call.arguments).get("intent")
            except (ValueError, AttributeError):
                return "(invalid_args)"
            if intent in _INTENT_LABELS:
                return intent
            return "(invalid_label)"
        return "(no_tool_call)"

    try:
        predictions = await asyncio.gather(
            *(classify(case["message"]) for case in cases)
        )
    finally:
        await client.close()

    total_hits = 0
    tag_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    failures: list[tuple[str, str, str]] = []
    for case, predicted in zip(cases, predictions):
        hit = predicted == case["expected_intent"]
        total_hits += hit
        for tag in case["tags"]:
            tag_stats[tag][0] += hit
            tag_stats[tag][1] += 1
        if not hit:
            failures.append(
                (case["message"], case["expected_intent"], predicted))

    print("=" * 60)
    print(f"FC 意图分类（model={llm.model}，共 {len(cases)} 条）")
    print(f"  准确率: {total_hits}/{len(cases)} = {total_hits / len(cases):.1%}")
    print("  分 tag 明细:")
    for tag, (hit, total) in sorted(tag_stats.items()):
        print(f"    {tag:<15} {hit}/{total} = {hit / total:.1%}")
    if verbose and failures:
        print("  错误用例（message | 期望 -> 实际）:")
        for message, expected, actual in failures:
            print(f"    {message} | {expected} -> {actual}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 意图/检索离线评测")
    parser.add_argument("--verbose", action="store_true", help="列出每条错误用例")
    parser.add_argument(
        "--with-embedding",
        action="store_true",
        help="附加运行 embedding 检索对比（需网络与 embedding 配置，非基线）",
    )
    parser.add_argument(
        "--fc",
        action="store_true",
        help="附加运行 FC 版意图评测（需真实 LLM key，产生 API 计费，非基线）",
    )
    args = parser.parse_args()

    evaluate_intent(args.verbose)
    evaluate_retrieval(args.verbose, with_embedding=False)
    if args.with_embedding:
        evaluate_retrieval(args.verbose, with_embedding=True)
    if args.fc:
        asyncio.run(evaluate_intent_fc(args.verbose))
    print("=" * 60)


if __name__ == "__main__":
    main()
