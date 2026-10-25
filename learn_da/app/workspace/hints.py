"""分级提示（ladder）的层级计算与确定性文案（改版 E2）。

设计稿 §8.2 把 AI 介入分三档，其中 ladder 是「用户点『给点提示』」这一档：
服务端按**真实失败次数**算层级，写 ``hint_usages``，越层请求无效。

层级公式（服务端权威）::

    level = min(3, 1 + hints_used + failures_since_last_hint // 2)

* ``hints_used`` —— 该任务已经用过几层提示（这是梯子本身的「第几级」）；
* ``failures_since_last_hint`` —— 该任务在「上一次提示之后」又失败了几次，
  **每两次失败相当于多爬一级**。

为什么失败只按「每两次一级」折算：早期按设计稿原式
``min(3, 1 + failures_since_last_hint + hints_used)`` 实现后实测发现梯子只有
两级可用——只要失败过一次再点提示就直接是 L2（把学习者已经看到的实际值
再说一遍），失败两次就顶到 L3，而最轻的 L1（只指方向、不给实际值）几乎
永远拿不到。改成「失败两次折一级」之后：失败 1 次先给 L1，连续失败 4 次
才到 L3；同时「连续失败 5 次但不提问」仍能拿到 L3，旧实现「真卡住的人拿
不到有效帮助」的问题没有回来。

这条公式替代了改版 E1 之前那个**错误的代理指标**：旧实现用
``AgentInteraction`` 的条数（即「在这门课里问了几次」）当作层级依据，
于是「连问 5 个概念问题」会被判成 L3（没卡住的人拿到接近答案的提示），
而「连续失败 5 次但没提问」永远是 L1（真卡住的人拿不到有效帮助）。

文案不调用模型：三层各自披露多少信息是确定性的，逐层加深但**始终不给
整格可提交代码**（用户已明确 AI 只解释、不改代码）。第 2、3 层用到的
诊断信息全部来自断言运行时已经回传的 ``detail`` / ``actual``，不额外猜。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

HINT_MAX_LEVEL = 3

#: 封顶后再点提示时追加的一句（避免同一层原样重复却装作又深入了一层）
_CAPPED_NOTICE = (
    "\n**这已经是最后一层提示**，再点也不会更深。如果还是卡住，"
    "把这段报错连同你这一格的代码发到右栏的 AI 助手，让它针对具体"
    "一行解释；或者回看任务要求里那句「验收标准」。"
)

#: 「缺少列 ['revenue']（实际列：['region', 'quantity', 'orders']）」
_MISSING_COLUMNS = re.compile(r"缺少列\s*\[([^\]]*)\]")
#: 断言 detail/actual 里可读的列名字面量
_QUOTED = re.compile(r"'([^']+)'")
#: polars/duckdb 找不到列时的可用列提示：
#: ``unable to find column "revenue"; valid columns: ["region", "quantity"]``
_VALID_COLUMNS = re.compile(r"valid columns:\s*\[([^\]]*)\]", re.IGNORECASE)
#: 报错里被引号包住的列名（polars 用双引号，旧代码用单引号）
_ERROR_QUOTED = re.compile(r"[\"'`]([A-Za-z_][A-Za-z0-9_]*)[\"'`]")
#: 异常类名，如 ``polars.exceptions.ColumnNotFoundError``
_ERROR_CLASS = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception))\b")
#: 行首的 ``polars.exceptions.ColumnNotFoundError: `` 前缀（可带模块路径）
_ERROR_PREFIX = re.compile(
    r"^(?P<cls>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))\s*:\s*"
)

#: 断言失败时的常见原因（按 detail 关键词匹配，只用于 L2/L3 的「该查什么」）
_REASON_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("缺少列", "unable to find column", "ColumnNotFound"),
        "结果的列名对不上：多半是聚合之后没有 alias，或者聚合写在了别的列上。",
    ),
    (
        ("height",),
        "行数对不上：先确认过滤条件、分组键，以及有没有漏掉某一格。",
    ),
    (
        ("sum", "合计"),
        "合计对不上：先确认聚合的是哪一列，以及过滤范围是否和任务要求一致。",
    ),
    (
        ("to_list", "sorted"),
        "取值或顺序对不上：确认排序方向（descending=True）和截取的行数。",
    ),
    (
        ("dtype", "类型"),
        "类型对不上：该做显式转换（例如 str.to_date / cast）而不是让它保持字符串。",
    ),
)

#: 第 2 层可以点名的 API（按原因归类，只给名称不给完整语句）
_API_BY_RULE: dict[str, str] = {
    "缺少列": "`.alias(...)` 给聚合结果命名，`pl.col(...)` 选中要聚合的列",
    "unable to find column": (
        "`.alias(...)` 给聚合结果命名；引用列用 `pl.col(\"列名\")`，"
        "引用上一格的变量直接用变量名"
    ),
    "height": "`.filter(...)` 收窄范围、`group_by(...)` 决定分组粒度",
    "sum": "`.agg(pl.col(...).sum())` 的列选择，以及 `filter` 的范围",
    "to_list": "`.sort(..., descending=True)` 与 `.head(n)` / `.slice(0, n)`",
    "dtype": "`.cast(...)`、`str.to_date(...)`、`str.strip_chars()`",
    "默认": "先 `print()` 出中间结果的 `shape` 与 `columns`，再对照任务要求逐项核对",
}


def compute_level(failures_since_last_hint: int, hints_used: int) -> int:
    """按「已用层数 + 每两次失败折一级」算层级，并钳制在 1..3。"""
    failures = max(0, int(failures_since_last_hint))
    raw = 1 + max(0, int(hints_used)) + failures // 2
    return max(1, min(HINT_MAX_LEVEL, raw))


@dataclass(frozen=True)
class HintState:
    """某任务的提示进度（全部来自服务端记录）。

    后三个字段给了默认值，方便测试与「还没有任何记录」的场景直接构造；
    真实计算一律走 ``compute_level``（见 ``repository.hint_state``）。
    """

    task_id: str
    failures_since_last_hint: int = 0
    hints_used: int = 0
    level: int = 1
    last_hint_at: Any = None

    @property
    def next_level(self) -> int:
        """点一次提示后能拿到的层级（= 当前 level，因为 level 就是「下一次」）。"""
        return self.level


def _rule_for(texts: Iterable[str]) -> str:
    joined = " ".join(t for t in texts if t)
    for keywords, reason in _REASON_RULES:
        if any(keyword in joined for keyword in keywords):
            return reason
    return ""


def _api_hint(texts: Iterable[str]) -> str:
    joined = " ".join(t for t in texts if t)
    for keywords, api in _API_BY_RULE.items():
        if keywords != "默认" and keywords in joined:
            return api
    return _API_BY_RULE["默认"]


def _missing_columns(texts: Iterable[str]) -> list[str]:
    found: list[str] = []
    for text in texts:
        match = _MISSING_COLUMNS.search(text or "")
        if match:
            for name in _QUOTED.findall(match.group(1)):
                if name not in found:
                    found.append(name)
    return found


def normalize_error(message: str) -> str:
    """把重复的异常前缀压成一句可读的话（``短类名: 摘要``）。

    真实 stderr 末行长这样，直接贴给学习者会看到类名重复两次::

        ColumnNotFoundError: polars.exceptions.ColumnNotFoundError:
            unable to find column "revenue"; valid columns: [...]

    这里把所有 ``xxxError: `` 前缀逐个剥掉，只保留第一个类名的短形式，
    摘要部分原样保留（列名与 valid columns 都在摘要里，不能丢）。
    """
    text = " ".join((message or "").split())
    if not text:
        return ""

    first_class = ""
    rest = text
    while True:
        match = _ERROR_PREFIX.match(rest)
        if not match:
            break
        class_name = match.group("cls").split(".")[-1]
        if not first_class:
            first_class = class_name
        rest = rest[match.end() :].strip()
        if not rest:
            break

    if first_class and rest:
        return f"{first_class}: {rest}"[:300]
    return text[:300]


def _valid_columns(texts: Iterable[str]) -> list[str]:
    """从报错里取「当前实际有哪些列」（polars 的 valid columns 提示）。"""
    found: list[str] = []
    for text in texts:
        match = _VALID_COLUMNS.search(text or "")
        if not match:
            continue
        for name in _ERROR_QUOTED.findall(match.group(1)):
            if name not in found:
                found.append(name)
    return found


def _error_column(texts: Iterable[str]) -> str:
    """报错点名的那个列/变量名（``unable to find column "revenue"``）。"""
    for text in texts:
        candidate = (text or "").strip()
        if not candidate:
            continue
        valid = set(_valid_columns([candidate]))
        for name in _ERROR_QUOTED.findall(candidate):
            if name not in valid:
                return name
    return ""


def _failed_titles(assertions: list[dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    for item in assertions:
        if str(item.get("status") or "") == "passed":
            continue
        title = str(item.get("title") or item.get("id") or "").strip()
        if title and title not in titles:
            titles.append(title)
    return titles


def build_hint_content(
    level: int,
    *,
    task_title: str,
    task_objective: str,
    assertions: list[dict[str, Any]],
    execution_failure: str = "",
    hints_used: int = 0,
) -> str:
    """生成某一层的确定性提示文案。

    ``assertions`` 是最近一次提交的断言结果（含 ``detail`` / ``actual``）；
    ``execution_failure`` 是「代码根本没跑通」时的真实报错（来自单元格 stderr），
    有它时优先于断言结果——此时断言全是 skipped，说明不了问题；
    ``hints_used`` 用于判断这一层是不是「已经给过的同一层」，避免原样重复。
    """
    level = max(1, min(HINT_MAX_LEVEL, int(level)))
    failure = normalize_error(execution_failure)
    titles = _failed_titles(assertions)
    texts = [
        str(item.get("detail") or "") + " " + str(item.get("actual") or "")
        for item in assertions
    ]
    if failure:
        texts = [failure, *texts]
    reason = _rule_for(texts)
    api = _api_hint(texts)
    missing = _missing_columns(texts)
    valid_columns = _valid_columns([failure]) if failure else []
    error_column = _error_column([failure]) if failure else []

    lines: list[str] = [f"**提示 L{level}／{HINT_MAX_LEVEL}**"]

    if not titles and not failure:
        # 还没有失败记录：只能给「先做一次」的方向，不编造具体错误
        lines.append(
            "这个任务还没有可用的失败记录。先完整跑一遍当前格并提交，"
            "我才能对着真实的断言结果给提示。"
        )
        if task_objective:
            lines.append(f"\n任务要求：{task_objective.strip()}")
        return "\n".join(lines)

    lines.append(f"任务：{task_title}")

    if failure:
        # 代码没跑通：先说清「是哪一步崩的、报的什么错」，这是唯一有用的信息
        lines.append("这一格在运行时直接报错了，所以断言还没有机会执行。")
        lines.append(f"\n**报错**：`{failure}`")
        if valid_columns:
            joined = "、".join(f"`{name}`" for name in valid_columns[:6])
            lines.append(f"这一格此刻真正能用的列是：{joined}。")
        if level == 1:
            if error_column:
                lines.append(
                    f"\n**先定位**：`{error_column}` 这一格取不到。看它是不是"
                    "上一格产出的变量名，或者是不是某一列没起别名就被引用了。"
                )
            else:
                lines.append(
                    "\n**先定位这一行**：报错里的名字就是问题所在——检查它是不是"
                    "上一格产出的变量，或者列名是不是写错/没起别名。"
                )
            return "\n".join(lines)
        if reason:
            lines.append(f"\n**常见原因**：{reason}")
        lines.append(f"**可以查的 API**：{api}")
        if level == 2:
            return "\n".join(lines)
        if missing:
            joined = "、".join(f"`{name}`" for name in missing[:5])
            lines.append(f"\n**要改的地方**：结果里缺 {joined}，补上对应的列或别名。")
        elif error_column and valid_columns:
            joined = "、".join(f"`{name}`" for name in valid_columns[:6])
            lines.append(
                f"\n**要改的地方**：把 `{error_column}` 换成上一步真实存在的列名"
                f"（{joined} 之一），或者在这一格前面先把 `{error_column}` 算出来。"
            )
        else:
            lines.append(
                "\n**要改的地方**：把报错点出来的那个名字（变量或列）改成上一格"
                "真正产出的名字，别在这一格里重新定义它。"
            )
        lines.append(
            "- 改完只重跑这一格，确认不再报错、断言从失败变成通过，再提交任务。"
        )
        if hints_used >= HINT_MAX_LEVEL:
            lines.append(_CAPPED_NOTICE)
        return "\n".join(lines)

    lines.append("还没通过的断言：")
    for title in titles[:4]:
        lines.append(f"- {title}")

    if level == 1:
        lines.append(
            "\n**先看现象，不要急着改结构**：把这一格 `print()` 出来的"
            "`columns` 与 `shape` 和你任务要求里要的列、行数逐项对照。"
        )
        return "\n".join(lines)

    # L2：补上运行时已经回传的实际值 + 常见原因 + 可以用的 API 名称
    details: list[str] = []
    for item in assertions:
        if str(item.get("status") or "") == "passed":
            continue
        detail = str(item.get("detail") or "").strip()
        actual = str(item.get("actual") or "").strip()
        line = detail or actual
        if line and line not in details:
            details.append(line)
    if details:
        lines.append("\n**服务端判定给出的实际值**：")
        for line in details[:3]:
            lines.append(f"- {line}")
    if reason:
        lines.append(f"\n**常见原因**：{reason}")
    lines.append(f"**可以查的 API**：{api}")
    if level == 2:
        return "\n".join(lines)

    # L3：指出要改的那一处，但仍不给整格代码
    lines.append("\n**要改的地方**：")
    if missing:
        joined = "、".join(f"`{name}`" for name in missing[:5])
        lines.append(
            f"- 结果里缺 {joined}：在聚合表达式的末尾补 `.alias(...)`，"
            "名字要和任务要求完全一致（大小写、下划线都算）。"
        )
    elif reason:
        lines.append(f"- {reason}")
    else:
        lines.append("- 对照任务要求逐项核对最后一格的输出，差异通常就在最后一步。")
    lines.append(
        "- 改完只重跑这一格，确认断言从失败变成通过，再提交任务；"
        "不要整格重写，否则前面的格会一起失效。"
    )
    if hints_used >= HINT_MAX_LEVEL:
        # 已经封顶：再点一次拿到的还是同一层，不要假装给了新东西
        lines.append(_CAPPED_NOTICE)
    return "\n".join(lines)
