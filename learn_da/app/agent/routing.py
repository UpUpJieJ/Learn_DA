from dataclasses import dataclass

from .schemas import ToolName


@dataclass(frozen=True)
class AgentRoute:
    tool_name: ToolName
    confidence: float
    reason: str
    matched_keyword: str | None = None


class AgentRouter:
    rules: tuple[tuple[ToolName, tuple[str, ...], float, str], ...] = (
        (
            "fix_code",
            ("报错", "错误", "error", "fix", "修复"),
            0.88,
            "用户正在排查代码错误或请求修复",
        ),
        (
            "explain_code",
            ("解释", "explain", "作用", "什么意思"),
            0.82,
            "用户希望理解代码或概念",
        ),
        (
            "generate_exercise",
            ("练习", "exercise", "题目", "出题"),
            0.82,
            "用户希望生成练习任务",
        ),
        (
            "suggest_next_step",
            ("下一步", "next step", "继续学", "学什么", "接下来"),
            0.82,
            "用户希望获得学习路径建议",
        ),
        (
            "generate_example_code",
            ("duckdb", "polars", "示例", "example", "代码"),
            0.72,
            "用户希望获得数据分析示例或代码",
        ),
    )

    def resolve(self, message: str) -> AgentRoute:
        text = message.lower()
        for tool_name, keywords, confidence, reason in self.rules:
            matched_keyword = self._first_match(text, keywords)
            if matched_keyword:
                return AgentRoute(
                    tool_name=tool_name,
                    confidence=confidence,
                    reason=reason,
                    matched_keyword=matched_keyword,
                )
        return AgentRoute(
            tool_name="general_chat",
            confidence=0.45,
            reason="未命中明确工具意图，使用通用学习助手回复",
            matched_keyword=None,
        )

    def _first_match(self, text: str, keywords: tuple[str, ...]) -> str | None:
        for keyword in keywords:
            if keyword.lower() in text:
                return keyword
        return None
