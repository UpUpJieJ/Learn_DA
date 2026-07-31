"""
Task 3: 受限确定性验证器单测

验收标准：
- 结果只由执行输出和练习定义决定
- 执行错误不会误标成练习失败（而是 unverifiable）
- 禁止 eval、动态 import、内容可执行脚本和 LLM
"""

import pytest

from app.practice.validator import (
    VerificationResult,
    verify,
    _normalize_stdout,
    _verify_stdout_exact,
    _verify_stdout_contains,
    _verify_dataframe_rows,
)


# =====================================================
# stdout_exact
# =====================================================


class TestStdoutExact:
    """精确匹配 stdout"""

    def test_exact_match_passes(self):
        result = verify("stdout_exact", "100", stdout="100\n")
        assert result.status == "passed"

    def test_exact_match_with_whitespace(self):
        """首尾空白被规范化"""
        result = verify("stdout_exact", "100", stdout="  100  \n")
        assert result.status == "passed"

    def test_mismatch_fails(self):
        result = verify("stdout_exact", "100", stdout="99\n")
        assert result.status == "failed"
        assert result.failure_reason == "stdout_exact_mismatch"

    def test_empty_stdout_fails_when_expected_nonempty(self):
        result = verify("stdout_exact", "hello", stdout="")
        assert result.status == "failed"

    def test_multiline_exact(self):
        result = verify("stdout_exact", "line1\nline2", stdout="line1\nline2\n")
        assert result.status == "passed"


# =====================================================
# stdout_contains
# =====================================================


class TestStdoutContains:
    """检查 stdout 是否包含所有期望字符串"""

    def test_single_string_contains(self):
        result = verify("stdout_contains", "键盘", stdout="键盘 显示器 耳机")
        assert result.status == "passed"

    def test_list_all_present(self):
        result = verify(
            "stdout_contains",
            ["键盘", "显示器", "耳机"],
            stdout="shape: (3, 2)\n键盘 200\n显示器 1500\n耳机 300",
        )
        assert result.status == "passed"

    def test_list_missing_one(self):
        result = verify(
            "stdout_contains",
            ["键盘", "鼠标"],
            stdout="键盘 200",
        )
        assert result.status == "failed"
        assert result.failure_reason == "stdout_contains_missing"

    def test_invalid_expected_type(self):
        """expected 非 str/list → unverifiable"""
        result = verify("stdout_contains", 12345, stdout="12345")
        assert result.status == "unverifiable"
        assert "invalid_expected" in result.failure_reason


# =====================================================
# dataframe_rows
# =====================================================


class TestDataframeRows:
    """检查 DataFrame 结果"""

    def test_columns_match(self):
        df = {"columns": ["product", "price"], "rows": [], "row_count": 3}
        result = verify(
            "dataframe_rows",
            {"columns": ["product", "price"]},
            stdout="",
            dataframe=df,
        )
        assert result.status == "passed"

    def test_missing_columns_fails(self):
        df = {"columns": ["product"], "rows": [], "row_count": 3}
        result = verify(
            "dataframe_rows",
            {"columns": ["product", "price"]},
            stdout="",
            dataframe=df,
        )
        assert result.status == "failed"
        assert result.failure_reason == "dataframe_rows_missing_columns"

    def test_row_count_match(self):
        df = {"columns": ["a"], "rows": [], "row_count": 5}
        result = verify(
            "dataframe_rows",
            {"row_count": 5},
            stdout="",
            dataframe=df,
        )
        assert result.status == "passed"

    def test_row_count_mismatch(self):
        df = {"columns": ["a"], "rows": [], "row_count": 3}
        result = verify(
            "dataframe_rows",
            {"row_count": 5},
            stdout="",
            dataframe=df,
        )
        assert result.status == "failed"
        assert result.failure_reason == "dataframe_rows_row_count_mismatch"

    def test_min_rows_passes(self):
        df = {"columns": ["a"], "rows": [], "row_count": 10}
        result = verify(
            "dataframe_rows",
            {"min_rows": 5},
            stdout="",
            dataframe=df,
        )
        assert result.status == "passed"

    def test_min_rows_fails(self):
        df = {"columns": ["a"], "rows": [], "row_count": 2}
        result = verify(
            "dataframe_rows",
            {"min_rows": 5},
            stdout="",
            dataframe=df,
        )
        assert result.status == "failed"
        assert result.failure_reason == "dataframe_rows_too_few_rows"

    def test_no_dataframe_unverifiable(self):
        """无 DataFrame 输出 → unverifiable"""
        result = verify(
            "dataframe_rows",
            {"columns": ["a"]},
            stdout="no df here",
            dataframe=None,
        )
        assert result.status == "unverifiable"
        assert "no_dataframe" in result.failure_reason

    def test_invalid_expected_unverifiable(self):
        """expected 非 dict → unverifiable"""
        df = {"columns": ["a"], "rows": [], "row_count": 1}
        result = verify("dataframe_rows", "bad", stdout="", dataframe=df)
        assert result.status == "unverifiable"


# =====================================================
# 执行错误不误判
# =====================================================


class TestExecutionErrorNotMisjudged:
    """执行错误 → unverifiable，不是 failed"""

    @pytest.mark.parametrize("status", ["error", "timeout", "rejected", "unavailable"])
    def test_non_success_execution_is_unverifiable(self, status):
        result = verify(
            "stdout_exact",
            "100",
            stdout="",
            execution_status=status,
        )
        assert result.status == "unverifiable"
        assert f"execution_{status}" in result.failure_reason

    def test_success_execution_proceeds_to_verify(self):
        """执行成功才进入判定"""
        result = verify(
            "stdout_exact",
            "100",
            stdout="100",
            execution_status="success",
        )
        assert result.status == "passed"


# =====================================================
# 未知判定器
# =====================================================


class TestUnknownValidator:
    """未知 validator type → unverifiable"""

    def test_unknown_type(self):
        result = verify("llm_judge", "x", stdout="x")
        assert result.status == "unverifiable"
        assert "unknown_validator" in result.failure_reason


# =====================================================
# 规范化
# =====================================================


class TestNormalization:
    """stdout 规范化"""

    def test_strip_whitespace(self):
        assert _normalize_stdout("  hello  \n") == "hello"

    def test_empty_string(self):
        assert _normalize_stdout("") == ""

    def test_preserves_internal_newlines(self):
        assert _normalize_stdout("a\nb\n") == "a\nb"
