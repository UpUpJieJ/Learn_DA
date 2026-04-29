import re

from .schemas import (
    AgentCodeBlock,
    AgentResultSection,
    AgentStructuredResult,
    ToolName,
)


SECTION_RE = re.compile(r"^([^：:\n]{1,30})[：:]\s*$")
CODE_BLOCK_RE = re.compile(r"```([a-zA-Z0-9_+-]+)?\s*\n(.*?)\n```", re.DOTALL)


def parse_structured_result(tool_name: ToolName, content: str) -> AgentStructuredResult:
    return AgentStructuredResult(
        kind=tool_name,
        sections=_parse_sections(content),
        code_blocks=_parse_code_blocks(content),
    )


def _parse_sections(content: str) -> list[AgentResultSection]:
    sections: list[AgentResultSection] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in content.splitlines():
        match = SECTION_RE.match(line.strip())
        if match:
            _append_section(sections, current_title, current_lines)
            current_title = match.group(1).strip()
            current_lines = []
            continue
        current_lines.append(line)

    _append_section(sections, current_title, current_lines)
    if sections:
        return sections

    stripped = content.strip()
    if not stripped:
        return []
    return [AgentResultSection(title="回答", content=stripped)]


def _append_section(
    sections: list[AgentResultSection],
    title: str | None,
    lines: list[str],
) -> None:
    if title is None:
        return
    content = "\n".join(lines).strip()
    sections.append(AgentResultSection(title=title, content=content))


def _parse_code_blocks(content: str) -> list[AgentCodeBlock]:
    blocks: list[AgentCodeBlock] = []
    for match in CODE_BLOCK_RE.finditer(content):
        language = match.group(1) or None
        code = match.group(2).strip()
        blocks.append(AgentCodeBlock(language=language, code=code))
    return blocks
