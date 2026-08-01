from .evidence import AgentLearningEvidence
from .schemas import AgentChatMessage, AgentContext


SYSTEM_PROMPT = (
    "你是 Learn DA 的通用学习教练，帮助学习者围绕当前课程理解概念、练习代码并规划下一步。"
    "回答必须简洁、可执行，并始终围绕当前课程和 Playground 上下文。"
    "你不是代写工具，也不是泛聊天助手。"
    "如果当前课程涉及 Polars、DuckDB、Pandas 或 SQL，可以用对比方式讲解关键差异；其他主题则优先解释核心概念和练习方法。"
    "先解释思路，再给代码或操作建议；在练习场景里优先给提示，不要直接给最终答案，除非用户明确要求。"
    "修复错误时，不仅要告诉用户怎么改，还要解释为什么会错、如何验证修复是否生效。"
    "如果用户在问下一步，优先给 1 到 3 个最值得执行的动作，不要铺开成长清单。"
    "如果信息不足，先给最可能原因和一个可验证的下一步，不要编造不存在的 API。"
    "除非用户明确要求，不要输出长篇背景知识。"
)

# 阶段 ④ FC 路径的系统提示：工具只读、按需调用、正文不带意图标签
FC_SYSTEM_PROMPT = SYSTEM_PROMPT + (
    "你可以调用只读工具查询课程知识、学习进度和下一步学习建议；"
    "只在回答需要事实依据时调用工具，拿到结果后综合成简洁回答。"
    "学习建议以工具返回的规则引擎结果为准，不要自行改变推荐顺序。"
    "回答正文直接开始，首行不要输出任何意图标签、分类前缀或格式说明。"
)


def build_fc_chat_messages(
    user_message: str,
    history: list[AgentChatMessage],
    context: AgentContext | None,
    max_turns: int,
) -> list[dict[str, str]]:
    """FC 路径的消息构造：不注入 response_format 模板，结构由工具调用承载。"""
    messages = [{"role": "system", "content": FC_SYSTEM_PROMPT}]
    context_block = build_context_block(context)
    if context_block:
        messages.append({"role": "system", "content": context_block})
    messages.extend(compact_history(history, max_turns=max_turns))
    messages.append({"role": "user", "content": user_message})
    return messages


def compact_history(
    history: list[AgentChatMessage],
    max_turns: int,
) -> list[dict[str, str]]:
    recent = history[-max_turns * 2:]
    return [{"role": item.role, "content": item.content} for item in recent]


def build_context_block(context: AgentContext | None) -> str:
    """构造课程/编辑器展示上下文。

    阶段 3 起，stdout/stderr/lastError 不再注入本块——练习执行/验证状态
    由服务端 ``AgentEvidenceResolver`` 解析并写入独立的证据块，避免客户端
    自报值进入教学判断。当前编辑器代码（currentCode）仍保留，供用户显式
    请求解释或排错时模型参考。
    """
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
    return "\n\n".join(parts)


def build_evidence_block(evidence: AgentLearningEvidence | None) -> str:
    """构造服务端练习证据块（权威来源）。

    始终注入到 FC prompt；无证据时显式说明，避免模型臆造练习状态。
    """
    if evidence is None:
        return "【服务端练习证据】\n状态：学习者暂无可用练习证据"

    lines = ["【服务端练习证据】"]
    state_label = {
        "execution_failed": "代码执行失败",
        "verification_failed": "执行成功但验证未通过",
        "passed_unconfirmed": "练习已通过",
        "unverifiable": "结果不可验证",
        "no_evidence": "暂无可用练习证据",
    }.get(evidence.state, evidence.state)
    lines.append(f"教学状态：{evidence.state}（{state_label}）")

    if evidence.attempt_id is not None:
        lines.append(f"尝试 ID：{evidence.attempt_id}")
    if evidence.lesson_slug:
        lines.append(f"课程：{evidence.lesson_slug}")
    if evidence.exercise_id:
        lines.append(f"练习：{evidence.exercise_id}")
    if evidence.execution_status:
        lines.append(f"执行状态：{evidence.execution_status}")
    if evidence.verification_status:
        lines.append(f"验证状态：{evidence.verification_status}")
    if evidence.failure_reason:
        lines.append(f"失败原因：{evidence.failure_reason[:300]}")
    if evidence.duration_ms is not None:
        lines.append(f"耗时：{evidence.duration_ms}ms")
    if evidence.stdout_summary:
        lines.append(f"标准输出摘要：\n{evidence.stdout_summary}")
    if evidence.stderr_summary:
        lines.append(f"标准错误摘要：\n{evidence.stderr_summary}")
    lines.append(
        "课程完成状态：" + ("已完成" if evidence.lesson_completed else "未完成")
    )
    if evidence.evidence_time:
        lines.append(f"证据时间：{evidence.evidence_time}")
    lines.append(
        "以上为服务端权威证据，客户端自报状态不可覆盖；回答时以此为准。"
    )
    return "\n".join(lines)


def build_chat_messages(
    user_message: str,
    history: list[AgentChatMessage],
    context: AgentContext | None,
    max_turns: int,
) -> list[dict[str, str]]:
    """降级路径的消息构造：格式模板已随 FC 默认开启下线。"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    context_block = build_context_block(context)
    if context_block:
        messages.append({"role": "system", "content": context_block})
    messages.extend(compact_history(history, max_turns=max_turns))
    messages.append({"role": "user", "content": user_message})
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
                "请修复这段学习代码。"
                "必须只给一个修复代码块，并保证代码块是完整可运行的 Python 代码。\n\n"
                f"错误信息：\n```text\n{error_message[:3000]}\n```\n\n"
                f"代码：\n```python\n{code[:8000]}\n```"
                f"{context_text}"
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
                f"{context_text}"
            ),
        },
    ]
