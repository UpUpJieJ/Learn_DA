"""
Phase 2: 可验证练习闭环 - 确定性判定器

纯函数验证器，基于执行输出和练习定义返回 verdict。
不依赖 eval、动态 import、内容可执行脚本或 LLM。

判定结果只由执行输出和练习定义决定，执行错误不会误标成练习失败。
"""

from __future__ import annotations

from typing import Any


class VerificationResult:
    """验证结果"""

    def __init__(
        self,
        status: str,  # passed / failed / unverifiable
        failure_reason: str | None = None,
        validator_type: str | None = None,
    ):
        self.status = status
        self.failure_reason = failure_reason
        self.validator_type = validator_type

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "failure_reason": self.failure_reason,
            "validator_type": self.validator_type,
        }


def verify(
    validator_type: str,
    expected: Any,
    *,
    stdout: str = "",
    stderr: str = "",
    execution_status: str = "success",
    dataframe: dict[str, Any] | None = None,
) -> VerificationResult:
    """执行确定性判定。

    Args:
        validator_type: 判定器类型（stdout_exact / stdout_contains / dataframe_rows）
        expected: 期望值
        stdout: 规范化后的标准输出
        stderr: 标准错误
        execution_status: 执行状态
        dataframe: DataFrame 结果（如有）

    Returns:
        VerificationResult: 验证结果
    """
    # 执行失败 → unverifiable（不是练习失败）
    if execution_status not in ("success",):
        return VerificationResult(
            status="unverifiable",
            failure_reason=f"execution_{execution_status}",
            validator_type=validator_type,
        )

    # 执行成功但有 stderr（警告）→ 仍可验证
    # 执行成功但无 stdout → 按判定器类型处理

    if validator_type == "stdout_exact":
        return _verify_stdout_exact(stdout, expected, validator_type)
    elif validator_type == "stdout_contains":
        return _verify_stdout_contains(stdout, expected, validator_type)
    elif validator_type == "dataframe_rows":
        return _verify_dataframe_rows(dataframe, expected, validator_type)
    else:
        return VerificationResult(
            status="unverifiable",
            failure_reason=f"unknown_validator_{validator_type}",
            validator_type=validator_type,
        )


def _normalize_stdout(stdout: str) -> str:
    """规范化 stdout：去除首尾空白、统一换行"""
    return stdout.strip()


def _verify_stdout_exact(
    stdout: str, expected: Any, validator_type: str
) -> VerificationResult:
    """精确匹配 stdout"""
    normalized = _normalize_stdout(stdout)
    expected_str = str(expected).strip() if expected is not None else ""

    if normalized == expected_str:
        return VerificationResult(status="passed", validator_type=validator_type)

    return VerificationResult(
        status="failed",
        failure_reason="stdout_exact_mismatch",
        validator_type=validator_type,
    )


def _verify_stdout_contains(
    stdout: str, expected: Any, validator_type: str
) -> VerificationResult:
    """检查 stdout 是否包含所有期望字符串"""
    normalized = _normalize_stdout(stdout)

    # expected 可以是单个字符串或字符串列表
    if isinstance(expected, str):
        expected_items = [expected]
    elif isinstance(expected, list):
        expected_items = [str(e) for e in expected]
    else:
        return VerificationResult(
            status="unverifiable",
            failure_reason="stdout_contains_invalid_expected",
            validator_type=validator_type,
        )

    missing = [e for e in expected_items if e not in normalized]
    if not missing:
        return VerificationResult(status="passed", validator_type=validator_type)

    return VerificationResult(
        status="failed",
        failure_reason="stdout_contains_missing",
        validator_type=validator_type,
    )


def _verify_dataframe_rows(
    dataframe: dict[str, Any] | None,
    expected: Any,
    validator_type: str,
) -> VerificationResult:
    """检查 DataFrame 结果是否满足预期行/列条件"""
    if dataframe is None:
        return VerificationResult(
            status="unverifiable",
            failure_reason="dataframe_rows_no_dataframe",
            validator_type=validator_type,
        )

    if not isinstance(expected, dict):
        return VerificationResult(
            status="unverifiable",
            failure_reason="dataframe_rows_invalid_expected",
            validator_type=validator_type,
        )

    # 检查列名
    expected_columns = expected.get("columns")
    if expected_columns is not None:
        actual_columns = set(dataframe.get("columns", []))
        required = set(expected_columns)
        if not required.issubset(actual_columns):
            return VerificationResult(
                status="failed",
                failure_reason="dataframe_rows_missing_columns",
                validator_type=validator_type,
            )

    # 检查行数
    expected_row_count = expected.get("row_count")
    if expected_row_count is not None:
        actual_row_count = dataframe.get("row_count", 0)
        if actual_row_count != expected_row_count:
            return VerificationResult(
                status="failed",
                failure_reason="dataframe_rows_row_count_mismatch",
                validator_type=validator_type,
            )

    # 检查最小行数
    min_rows = expected.get("min_rows")
    if min_rows is not None:
        actual_row_count = dataframe.get("row_count", 0)
        if actual_row_count < min_rows:
            return VerificationResult(
                status="failed",
                failure_reason="dataframe_rows_too_few_rows",
                validator_type=validator_type,
            )

    return VerificationResult(status="passed", validator_type=validator_type)
