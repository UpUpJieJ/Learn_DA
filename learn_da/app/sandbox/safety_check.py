import re

from .schemas import SafetyCheckResult


BLOCKED_PATTERNS: dict[str, str] = {
    r"\bimport\s+os\b": "禁止导入 os",
    r"\bimport\s+subprocess\b": "禁止导入 subprocess",
    r"\bimport\s+socket\b": "禁止导入 socket",
    r"\bimport\s+requests\b": "禁止导入 requests",
    r"\bfrom\s+os\b": "禁止导入 os",
    r"\bfrom\s+subprocess\b": "禁止导入 subprocess",
    r"\bopen\s*\(": "禁止直接读写文件",
    r"\beval\s*\(": "禁止执行 eval",
    r"\bexec\s*\(": "禁止执行 exec",
    r"__import__\s*\(": "禁止动态导入模块",
}


def validate_code(code: str) -> SafetyCheckResult:
    for pattern, reason in BLOCKED_PATTERNS.items():
        if re.search(pattern, code):
            return SafetyCheckResult(is_safe=False, reason=reason)
    return SafetyCheckResult(is_safe=True)
