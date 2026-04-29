from .schemas import AgentChatMessage, AgentContext, ToolName
from .tools import EXPLAIN_FORMAT, FIX_FORMAT, response_format_for_tool


SYSTEM_PROMPT = (
    "你是 Learn DA 的数据分析学习助手，专注 Polars、DuckDB、Python 数据分析和 SQL 学习。"
    "回答必须简洁、可执行、贴合当前课程和 Playground 上下文。"
    "如果信息不足，先给最可能原因和一个可验证的下一步，不要编造不存在的 API。"
    "除非用户明确要求，不要输出长篇背景知识。"
)


def compact_history(
    history: list[AgentChatMessage],
    max_turns: int,
) -> list[dict[str, str]]:
    recent = history[-max_turns * 2 :]
    return [{"role": item.role, "content": item.content} for item in recent]


def build_context_block(context: AgentContext | None) -> str:
    if not context:
        return ""

    parts: list[str] = []
    if context.current_lesson or context.lesson_title or context.lesson_category:
        lesson_title = context.lesson_title or "未命名课程"
        lesson_slug = context.current_lesson or "unknown"
        lesson_category = context.lesson_category or "未分类"
        parts.append(f"当前课程：{lesson_title}（{lesson_slug}，{lesson_category}）")
    if context.lesson_content:
        parts.append(f"课程内容摘要：\n{context.lesson_content[:3000]}")
    if context.current_code:
        parts.append(
            f"当前 Playground 代码：\n```python\n{context.current_code[:4000]}\n```"
        )
    if context.stdout:
        parts.append(f"最近一次标准输出：\n```text\n{context.stdout[:2000]}\n```")
    if context.stderr:
        parts.append(f"最近一次执行错误：\n```text\n{context.stderr[:2000]}\n```")
    if context.last_error:
        parts.append(f"最近一次执行错误：\n```text\n{context.last_error[:2000]}\n```")
    return "\n\n".join(parts)


def build_chat_messages(
    user_message: str,
    history: list[AgentChatMessage],
    context: AgentContext | None,
    max_turns: int,
    tool_name: ToolName = "general_chat",
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    context_block = build_context_block(context)
    if context_block:
        messages.append({"role": "system", "content": context_block})
    messages.extend(compact_history(history, max_turns=max_turns))
    messages.append(
        {
            "role": "user",
            "content": f"{user_message}\n\n{response_format_for_tool(tool_name)}",
        }
    )
    return messages


def build_fix_messages(
    code: str,
    error_message: str,
    context: AgentContext | None = None,
) -> list[dict[str, str]]:
    context_block = build_context_block(context)
    context_text = f"\n\n上下文：\n{context_block}" if context_block else ""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "请修复这段 Python/Polars/DuckDB 学习代码。"
                "必须只给一个修复代码块，并保证代码块是完整可运行的 Python 代码。\n\n"
                f"错误信息：\n```text\n{error_message[:3000]}\n```\n\n"
                f"代码：\n```python\n{code[:8000]}\n```"
                f"{context_text}\n\n{FIX_FORMAT}"
            ),
        },
    ]


def build_explain_messages(
    code: str,
    context: AgentContext | None = None,
) -> list[dict[str, str]]:
    context_block = build_context_block(context)
    context_text = f"\n\n上下文：\n{context_block}" if context_block else ""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "请解释这段代码的作用，保持简洁，并优先结合当前课程语境。\n\n"
                f"代码：\n```python\n{code[:8000]}\n```"
                f"{context_text}\n\n{EXPLAIN_FORMAT}"
            ),
        },
    ]
