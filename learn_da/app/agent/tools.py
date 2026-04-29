from dataclasses import dataclass

from .schemas import ToolName


@dataclass(frozen=True)
class AgentTool:
    name: ToolName
    response_format: str
    fallback_content: str


EXPLAIN_FORMAT = """必须按以下格式回复：
结论：
用 1-2 句话说明这段代码做什么。

关键步骤：
1. ...
2. ...
3. ...

容易混淆：
指出 1 个初学者最容易误解的点。

建议你试试：
给 1 个小改动，让用户能在 Playground 里验证。
"""


FIX_FORMAT = """必须按以下格式回复：
问题原因：
说明报错的直接原因。

修复方式：
说明你改了什么，以及为什么这样改。

修复代码：
```python
# 给出完整可运行代码
```

验证建议：
说明用户运行后应该看到什么。
"""


EXERCISE_FORMAT = """必须按以下格式回复：
练习目标：
说明这个练习要掌握的知识点。

任务：
1. ...
2. ...
3. ...

提示：
给 1-2 个必要提示，不要直接给完整答案。

完成后检查：
说明如何判断结果是否正确。
"""


NEXT_STEP_FORMAT = """必须按以下格式回复：
当前状态：
根据课程、代码和输出判断用户现在处在哪一步。

下一步：
1. ...
2. ...

为什么：
说明这一步如何衔接当前学习内容。

建议运行：
```python
# 可选；如果没有必要，可以写“无需新增代码”
```
"""


EXAMPLE_FORMAT = """必须按以下格式回复：
示例目标：
说明示例演示的知识点。

代码：
```python
# 优先给可在当前 Playground 运行的 Python 代码
```

观察结果：
说明运行后应该重点看什么。
"""


GENERAL_FORMAT = """必须按以下格式回复：
简短回答：
直接回答用户问题，控制在 3-5 句话内。

下一步建议：
给一个可以立刻操作的小步骤。
"""


AGENT_TOOLS: dict[ToolName, AgentTool] = {
    "generate_example_code": AgentTool(
        name="generate_example_code",
        response_format=EXAMPLE_FORMAT,
        fallback_content=(
            "示例目标：\n"
            "用 DuckDB 在 Python 中查询内存数据，并完成分组统计。\n\n"
            "代码：\n"
            "```python\n"
            "import duckdb\n\n"
            "rows = [\n"
            "    {'category': 'A', 'amount': 10},\n"
            "    {'category': 'A', 'amount': 15},\n"
            "    {'category': 'B', 'amount': 7},\n"
            "]\n\n"
            "result = duckdb.sql('''\n"
            "    SELECT category, COUNT(*) AS cnt, SUM(amount) AS total\n"
            "    FROM rows\n"
            "    GROUP BY category\n"
            "    ORDER BY total DESC\n"
            "''').df()\n\n"
            "print(result)\n"
            "```\n\n"
            "观察结果：\n"
            "重点看 category 是否被正确分组，以及 cnt、total 两列是否符合原始数据。"
        ),
    ),
    "generate_exercise": AgentTool(
        name="generate_exercise",
        response_format=EXERCISE_FORMAT,
        fallback_content=(
            "练习目标：\n"
            "练习筛选、派生列和分组聚合这三个常见数据分析动作。\n\n"
            "任务：\n"
            "1. 基于当前课程代码，修改一个筛选条件。\n"
            "2. 新增一个派生列，例如金额等级、是否达标或文本标签。\n"
            "3. 用分组聚合验证新列是否符合预期。\n\n"
            "提示：\n"
            "优先复用当前示例里的 DataFrame，先做小改动再运行。\n\n"
            "完成后检查：\n"
            "输出表格中应该能看到筛选后的行数变化，以及新增列或聚合结果。"
        ),
    ),
    "fix_code": AgentTool(
        name="fix_code",
        response_format=FIX_FORMAT,
        fallback_content=(
            "问题原因：\n"
            "我已经看到你在排查代码错误，但当前缺少完整代码或完整报错。\n\n"
            "修复方式：\n"
            "请把当前代码和完整报错一起发给我，我会定位具体原因。\n\n"
            "修复代码：\n"
            "```python\n"
            "# 等你提供完整代码后，我会在这里给出可运行版本\n"
            "```\n\n"
            "验证建议：\n"
            "重新运行修复代码，确认错误信息消失，并检查输出是否符合课程目标。"
        ),
    ),
    "explain_code": AgentTool(
        name="explain_code",
        response_format=EXPLAIN_FORMAT,
        fallback_content=(
            "结论：\n"
            "请把要解释的代码发给我，我会说明它在数据分析流程里完成了什么。\n\n"
            "关键步骤：\n"
            "1. 判断数据从哪里来。\n"
            "2. 识别 Polars 或 DuckDB 的核心 API。\n"
            "3. 解释输出结果应该如何阅读。\n\n"
            "容易混淆：\n"
            "同一个变量名可能在多次运行中被覆盖，需要结合当前 Playground 代码判断。\n\n"
            "建议你试试：\n"
            "先运行代码，再把输出结果一起发给我。"
        ),
    ),
    "suggest_next_step": AgentTool(
        name="suggest_next_step",
        response_format=NEXT_STEP_FORMAT,
        fallback_content=(
            "当前状态：\n"
            "你正在通过 Playground 学习数据分析代码，下一步适合把当前示例跑通并做一次小改造。\n\n"
            "下一步：\n"
            "1. 先运行当前示例，观察输出表格。\n"
            "2. 修改一个筛选条件或计算列，再运行一次对比结果。\n\n"
            "为什么：\n"
            "这样能确认你理解了 API 的输入、输出和数据变化，而不是只读过代码。\n\n"
            "建议运行：\n"
            "```python\n"
            "# 无需新增代码，先改当前示例中的一个条件并重新运行\n"
            "```"
        ),
    ),
    "general_chat": AgentTool(
        name="general_chat",
        response_format=GENERAL_FORMAT,
        fallback_content=(
            "简短回答：\n"
            "我已经收到你的问题。当前先使用降级回复，所以只能给一个通用建议。\n\n"
            "下一步建议：\n"
            "请补充当前课程、代码或报错，我会按更具体的上下文继续帮你。"
        ),
    ),
}


def get_agent_tool(tool_name: ToolName) -> AgentTool:
    return AGENT_TOOLS[tool_name]


def response_format_for_tool(tool_name: ToolName) -> str:
    return get_agent_tool(tool_name).response_format
