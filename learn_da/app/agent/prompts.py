from .evidence import AgentLearningEvidence
from .schemas import AgentChatMessage, AgentContext, AgentRecentRun


SYSTEM_PROMPT = (
    "你是 Learn DA 的通用学习助手，帮助学习者围绕当前课程理解概念、完成任务。"
    "回答必须简洁、可执行，并始终围绕当前课程与学习工作区上下文。"
    "你不是代写工具，也不是泛聊天助手。"
    "如果当前课程涉及 Polars、DuckDB、Pandas 或 SQL，可以用对比方式讲解关键差异；其他主题则优先解释核心概念和练习方法。"
    "先解释思路，再给代码或操作建议；在练习场景里优先给提示，不要直接给最终答案，除非用户明确要求。"
    "修复错误时，不仅要告诉用户怎么改，还要解释为什么会错、如何验证修复是否生效。"
    "任务顺序、完成状态与下一步该做哪个任务由服务端的任务列表权威给出；"
    "不要自行规划学习路线或建议跳过/重排任务，被问到下一步时让学习者看当前课程的任务列表。"
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


def build_recent_runs_block(runs: list[AgentRecentRun]) -> str:
    """最近几次单元格执行的摘要（客户端自报，只用于定位，不是教学证据）。

    草稿格或未提交的执行不会进 ``task_attempts``，服务端证据里看不到；
    但学习者问「刚才这个报错」时模型需要知道上下文，否则只能反问。
    """
    lines = ["最近的单元格执行（客户端自报，仅用于定位，判定以服务端证据为准）："]
    for run in runs[:3]:
        head = f"- {run.cell_id or '未知格'}：{run.status or '未知状态'}"
        if run.error_type:
            head += f"，{run.error_type}"
        if run.stderr_first_line:
            head += f" —— {run.stderr_first_line[:200]}"
        if run.assertions_failed:
            head += f"（未通过断言：{', '.join(run.assertions_failed[:5])}）"
        lines.append(head)
    return "\n".join(lines)


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
    if context.current_task:
        parts.append(f"当前任务：{context.current_task}")
    if context.session_id is not None:
        parts.append(f"工作区会话：{context.session_id}")
    if context.cell_id:
        parts.append(f"当前聚焦的单元格：{context.cell_id}")
    if context.recent_runs:
        parts.append(build_recent_runs_block(context.recent_runs))
    if context.current_code:
        parts.append(
            "编辑器里的当前代码（可能已改动但尚未提交，不代表服务端记录的状态）："
            f"\n```python\n{context.current_code[:4000]}\n```"
        )
    return "\n\n".join(parts)


HINT_LEVEL_DIRECTIVES: dict[int, str] = {
    1: "学习者刚开始求助。只指出方向与需要观察的现象，不要给具体改法。",
    2: "学习者已求助数次。可以说出出错的环节和要用的 API 名称，但不要写出完整语句。",
    3: "学习者多次卡在同一处。可以给出一行可复制的关键写法，但仍不要给出整格完整答案。",
}


def build_hint_directive(hint_level: int | None) -> str:
    """把服务端算出的提示层级转成模型能执行的指令。

    层级由 ``_resolve_hint_level`` 按真实求助次数决定；在改版 E1 之前它只
    回给前端展示，模型并不知道自己该给第几层，导致分级形同虚设。
    """
    if not hint_level:
        return ""
    level = max(1, min(3, int(hint_level)))
    directive = HINT_LEVEL_DIRECTIVES[level]
    return f"本次提示层级：L{level}（{directive}）"


def build_evidence_block(
    evidence: AgentLearningEvidence | None,
    hint_level: int | None = None,
) -> str:
    """构造服务端任务证据块（权威来源）。

    始终注入到 prompt；无证据时显式说明，避免模型臆造任务状态。
    ``hint_level`` 由服务端统计得出，写进块尾约束模型的提示深度。
    """
    hint_line = build_hint_directive(hint_level)
    if evidence is None:
        block = "【服务端任务证据】\n状态：学习者暂无可用任务证据"
        return f"{block}\n{hint_line}" if hint_line else block

    lines = ["【服务端任务证据】"]
    state_label = {
        "execution_failed": "代码执行失败",
        "verification_failed": "执行成功但断言未通过",
        "passed_unconfirmed": "任务已通过",
        "unverifiable": "结果不可验证",
        "no_evidence": "暂无可用任务证据",
    }.get(evidence.state, evidence.state)
    lines.append(f"教学状态：{evidence.state}（{state_label}）")

    if evidence.lesson_slug:
        lines.append(f"课程：{evidence.lesson_slug}")
    if evidence.tasks_passed is not None and evidence.tasks_total:
        lines.append(
            f"任务进度：{evidence.tasks_passed}/{evidence.tasks_total} 已通过"
        )
    if evidence.current_task_id:
        lines.append(f"当前未通过的任务：{evidence.current_task_id}")
    if evidence.attempt_id is not None:
        lines.append(f"提交 ID：{evidence.attempt_id}")
    if evidence.attempt_no is not None:
        lines.append(f"该任务第 {evidence.attempt_no} 次提交")
    if evidence.task_id:
        lines.append(f"本次提交的任务：{evidence.task_id}")
    if evidence.task_title:
        lines.append(f"任务标题：{evidence.task_title}")
    if evidence.task_objective:
        lines.append(f"任务要求：{evidence.task_objective}")
    if evidence.verdict:
        lines.append(f"判定结论：{evidence.verdict}")

    if evidence.assertions:
        lines.append("断言结果（失败在前）：")
        for index, item in enumerate(evidence.assertions, start=1):
            title = item.title or item.assertion_id or f"断言{index}"
            suffix = f"（{item.assertion_id}）" if item.assertion_id and item.title else ""
            lines.append(f"{index}. [{item.status or '未知'}] {title}{suffix}")
            if item.detail:
                lines.append(f"   说明：{item.detail}")
            if item.actual:
                lines.append(f"   实际值：{item.actual}")

    lines.append(
        "课程完成状态：" + ("已完成" if evidence.lesson_completed else "未完成")
    )
    if evidence.code_matches_editor is False:
        lines.append(
            "注意：编辑器里的代码不是最近一次提交的代码（可能已改动但未提交）。"
            "上面的断言结果是针对已提交版本的，不要用编辑器代码去反驳它，"
            "也不要据此说「你还缺 X」；如需判断当前代码，请让学习者先提交。"
        )
    if evidence.evidence_time:
        lines.append(f"证据时间：{evidence.evidence_time}")
    lines.append(
        "以上为服务端权威证据，客户端自报状态不可覆盖；回答时以此为准。"
        "给建议时只解释问题与方向，不要直接给出可提交的完整答案。"
    )
    if hint_line:
        lines.append(hint_line)
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
