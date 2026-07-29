from dataclasses import dataclass

from .schemas import ToolName


@dataclass(frozen=True)
class AgentTool:
    """降级文案注册表：response_format 模板已随 FC 默认开启下线。"""

    name: ToolName
    fallback_content: str


AGENT_TOOLS: dict[ToolName, AgentTool] = {
    "generate_example_code": AgentTool(
        name="generate_example_code",
        fallback_content=(
            "示例目标：\n"
            "演示如何把一个小知识点写成可运行的 Python 练习。\n\n"
            "代码：\n"
            "```python\n"
            "def add_bonus(score):\n"
            "    return score + 5\n\n"
            "scores = [80, 92, 76]\n"
            "for score in scores:\n"
            "    print(add_bonus(score))\n"
            "```\n\n"
            "观察结果：\n"
            "重点看函数是否被重复调用，以及每个输入是否得到对应输出。"
        ),
    ),
    "generate_exercise": AgentTool(
        name="generate_exercise",
        fallback_content=(
            "练习目标：\n"
            "围绕当前课程做一次小改造，确认你理解了输入、处理和输出。\n\n"
            "任务：\n"
            "1. 先运行当前示例，观察输出。\n"
            "2. 修改一个变量、参数或条件。\n"
            "3. 再运行一次，对比结果有什么变化。\n\n"
            "提示：\n"
            "优先做一个很小的改动，不要一次改太多。\n\n"
            "完成后检查：\n"
            "输出应该能清楚反映你刚才那处修改。"
        ),
    ),
    "fix_code": AgentTool(
        name="fix_code",
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
        fallback_content=(
            "结论：\n"
            "请把要解释的代码发给我，我会说明它在当前课程里完成了什么。\n\n"
            "关键步骤：\n"
            "1. 判断输入是什么。\n"
            "2. 识别关键语句或函数调用。\n"
            "3. 解释输出结果应该如何阅读。\n\n"
            "容易混淆：\n"
            "同一个变量名可能在多次运行中被覆盖，需要结合当前 Playground 代码判断。\n\n"
            "建议你试试：\n"
            "先运行代码，再把输出结果一起发给我。"
        ),
    ),
    "suggest_next_step": AgentTool(
        name="suggest_next_step",
        fallback_content=(
            "当前状态：\n"
            "你正在通过 Playground 学习当前课程，下一步适合把示例跑通并做一次小改造。\n\n"
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
