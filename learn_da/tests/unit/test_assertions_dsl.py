"""断言 DSL v2 骨架的行为测试（详设 §6）。

覆盖四型断言的正负例、"失败必须给 actual（截断 500）"、受限求值、
以及"程序末尾内联断言 → 子进程执行 → 解析标记行"这条真实链路。
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest

from app.practice import assertion_runtime
from app.practice.assertions import (
    ACTUAL_LIMIT,
    ASSERTION_MARKER,
    AssertionSpecError,
    evaluate_assertions,
    parse_assertion_output,
    render_assertion_source,
    summarize,
    validate_assertions,
)


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def test_validate_accepts_all_four_types():
    specs = validate_assertions(
        [
            {"id": "a1", "type": "expr_true", "expr": "x == 1"},
            {"id": "a2", "type": "frame_equal", "var": "df", "ref": "r1"},
            {"id": "a3", "type": "schema", "var": "df", "columns": ["a"]},
            {"id": "a4", "type": "sql_rows", "query": "select 1", "ref": "r2"},
        ]
    )
    assert [spec["type"] for spec in specs] == ["expr_true", "frame_equal", "schema", "sql_rows"]
    assert specs[1]["order_matters"] is True
    assert specs[3]["order_matters"] is False
    assert specs[3]["connection"] == "con"


@pytest.mark.parametrize(
    "raw, message",
    [
        ([{"type": "expr_true", "expr": "x"}], "缺少字符串 id"),
        ([{"id": "a", "type": "nope"}], "不受支持"),
        ([{"id": "a", "type": "expr_true"}], "缺少 expr"),
        ([{"id": "a", "type": "expr_true", "expr": "x.__class__"}], "双下划线"),
        ([{"id": "a", "type": "frame_equal", "ref": "r"}], "缺少 var"),
        ([{"id": "a", "type": "frame_equal", "var": "df"}], "缺少 ref"),
        ([{"id": "a", "type": "schema", "var": "df"}], "至少需要 columns 或 dtypes"),
        ([{"id": "a", "type": "schema", "var": "df", "columns": [1]}], "字符串列表"),
        ([{"id": "a", "type": "sql_rows", "ref": "r"}], "缺少 query"),
    ],
)
def test_validate_rejects_bad_specs(raw, message):
    with pytest.raises(AssertionSpecError) as excinfo:
        validate_assertions(raw)
    assert message in str(excinfo.value)


def test_validate_rejects_duplicate_ids():
    raw = [
        {"id": "a", "type": "expr_true", "expr": "True"},
        {"id": "a", "type": "expr_true", "expr": "True"},
    ]
    with pytest.raises(AssertionSpecError, match="重复"):
        validate_assertions(raw)


def test_missing_reference_is_rejected():
    with pytest.raises(AssertionSpecError, match="缺少参考结果"):
        render_assertion_source(
            [{"id": "a", "type": "frame_equal", "var": "df", "ref": "expected/x.parquet"}]
        )


# ---------------------------------------------------------------------------
# 四型断言
# ---------------------------------------------------------------------------


def test_expr_true_passes_and_reports_actual_on_failure():
    results = evaluate_assertions(
        [
            {"id": "ok", "type": "expr_true", "expr": "total == 6"},
            {"id": "bad", "type": "expr_true", "expr": "total == 5", "title": "总数应为 5"},
        ],
        {"total": 6},
    )
    assert results[0]["status"] == "passed"
    assert results[0]["actual"] is None
    assert results[1]["status"] == "failed"
    assert "实际值" in results[1]["actual"]
    assert results[1]["title"] == "总数应为 5"


def test_expr_true_cannot_import_or_call_open():
    results = evaluate_assertions(
        [{"id": "a", "type": "expr_true", "expr": "open('x') is None"}],
        {},
    )
    assert results[0]["status"] == "error"
    assert "NameError" in results[0]["actual"]


def test_frame_equal_compares_values_not_only_shape():
    df = pl.DataFrame({"region": ["华东", "华北"], "amount": [1.0, 2.0]})
    buffer = io.BytesIO()
    df.write_parquet(buffer)
    ref = buffer.getvalue()

    spec = [{"id": "a", "type": "frame_equal", "var": "df", "ref": "expected/r.parquet"}]
    assert evaluate_assertions(spec, {"df": df}, {"expected/r.parquet": ref})[0]["status"] == "passed"

    wrong = pl.DataFrame({"region": ["华东", "华北"], "amount": [1.0, 99.0]})
    failing = evaluate_assertions(spec, {"df": wrong}, {"expected/r.parquet": ref})[0]
    assert failing["status"] == "failed"
    assert "99.0" in failing["actual"]


def test_frame_equal_detects_extra_columns_and_rows():
    ref_buffer = __import__("io").BytesIO()
    pl.DataFrame({"amount": [1.0]}).write_parquet(ref_buffer)
    refs = {"expected/r.parquet": ref_buffer.getvalue()}
    spec = [{"id": "a", "type": "frame_equal", "var": "df", "ref": "expected/r.parquet"}]

    extra_column = pl.DataFrame({"amount": [1.0], "note": ["x"]})
    assert evaluate_assertions(spec, {"df": extra_column}, refs)[0]["status"] == "failed"

    extra_row = pl.DataFrame({"amount": [1.0, 1.0]})
    result = evaluate_assertions(spec, {"df": extra_row}, refs)[0]
    assert result["status"] == "failed"
    assert "行数不一致" in result["actual"]


def test_frame_equal_tolerance_and_row_order():
    df = pl.DataFrame({"a": [1.0, 2.0]})
    buffer = __import__("io").BytesIO()
    df.write_parquet(buffer)
    refs = {"r.parquet": buffer.getvalue()}

    close = pl.DataFrame({"a": [1.0, 2.0 + 1e-9]})
    spec = [{"id": "a", "type": "frame_equal", "var": "df", "ref": "r.parquet"}]
    assert evaluate_assertions(spec, {"df": close}, refs)[0]["status"] == "passed"

    reversed_df = pl.DataFrame({"a": [2.0, 1.0]})
    ordered = [dict(spec[0], order_matters=True)]
    unordered = [dict(spec[0], order_matters=False)]
    assert evaluate_assertions(ordered, {"df": reversed_df}, refs)[0]["status"] == "failed"
    assert evaluate_assertions(unordered, {"df": reversed_df}, refs)[0]["status"] == "passed"


def test_schema_checks_columns_and_dtypes():
    df = pl.DataFrame({"amount": [1.0], "order_date": ["2025-01-01"]})
    passing = evaluate_assertions(
        [{"id": "a", "type": "schema", "var": "df",
          "columns": ["amount", "order_date"], "dtypes": {"amount": "Float64"}}],
        {"df": df},
    )[0]
    assert passing["status"] == "passed"

    wrong_dtype = evaluate_assertions(
        [{"id": "a", "type": "schema", "var": "df", "dtypes": {"order_date": "Date"}}],
        {"df": df},
    )[0]
    assert wrong_dtype["status"] == "failed"
    assert "类型不一致" in wrong_dtype["actual"]


def test_schema_columns_are_containment_by_default_and_exact_on_demand():
    df = pl.DataFrame({"a": [1], "b": [2], "c": [3]})

    subset = evaluate_assertions(
        [{"id": "a", "type": "schema", "var": "df", "columns": ["a", "c"]}], {"df": df}
    )[0]
    assert subset["status"] == "passed", subset

    missing = evaluate_assertions(
        [{"id": "a", "type": "schema", "var": "df", "columns": ["a", "z"]}], {"df": df}
    )[0]
    assert missing["status"] == "failed"
    assert "缺少列 ['z']" in missing["actual"]

    exact = evaluate_assertions(
        [{"id": "a", "type": "schema", "var": "df", "columns": ["a", "b"], "exact": True}],
        {"df": df},
    )[0]
    assert exact["status"] == "failed"
    assert "完全一致" in exact["actual"]

    exact_ok = evaluate_assertions(
        [{"id": "a", "type": "schema", "var": "df", "columns": ["a", "b", "c"], "exact": True}],
        {"df": df},
    )[0]
    assert exact_ok["status"] == "passed"


def test_sql_rows_passes_and_reports_mismatch():
    import duckdb

    con = duckdb.connect()
    con.execute("create table orders(region varchar, amount double)")
    con.execute("insert into orders values ('华东', 10.0), ('华北', 20.0)")
    ref = json.dumps({"columns": ["region", "total"], "rows": [["华东", 10.0], ["华北", 20.0]]}).encode()
    spec = [{
        "id": "a", "type": "sql_rows", "ref": "r.json",
        "query": "select region, sum(amount) as total from orders group by 1",
    }]
    assert evaluate_assertions(spec, {"con": con}, {"r.json": ref})[0]["status"] == "passed"

    wrong_ref = json.dumps({"rows": [["华东", 99.0], ["华北", 20.0]]}).encode()
    failing = evaluate_assertions(spec, {"con": con}, {"r.json": wrong_ref})[0]
    assert failing["status"] == "failed"
    assert "不一致" in failing["actual"]


def test_missing_variable_is_an_assertion_error_not_user_failure():
    results = evaluate_assertions(
        [{"id": "a", "type": "frame_equal", "var": "nope", "ref": "r.parquet"}],
        {},
        {"r.parquet": b"PAR1"},
    )
    assert results[0]["status"] == "error"
    assert "不存在" in results[0]["actual"]


def test_actual_is_truncated():
    long_value = "x" * (ACTUAL_LIMIT * 2)
    ref_buffer = io.BytesIO()
    pl.DataFrame({"note": ["reference"]}).write_parquet(ref_buffer)
    result = evaluate_assertions(
        [{"id": "a", "type": "frame_equal", "var": "df", "ref": "r.parquet"}],
        {"df": pl.DataFrame({"note": [long_value]})},
        {"r.parquet": ref_buffer.getvalue()},
    )[0]
    assert result["status"] == "failed"
    assert len(result["actual"]) <= ACTUAL_LIMIT + len("...(截断)")
    assert result["actual"].endswith("...(截断)")


def test_summarize_points_at_the_first_failure():
    summary = summarize(
        [
            {"id": "a", "status": "passed"},
            {"id": "b", "status": "failed", "actual": "x"},
            {"id": "c", "status": "skipped"},
        ]
    )
    assert summary == {"total": 3, "passed": 1, "allPassed": False, "firstFailure": {"id": "b", "status": "failed", "actual": "x"}}


# ---------------------------------------------------------------------------
# 真实链路：内联到程序末尾 → 子进程 → 解析标记行
# ---------------------------------------------------------------------------


def test_assertions_run_inside_the_user_program(tmp_path):
    program = (
        "import polars as pl\n"
        "orders = pl.DataFrame({'region': ['华东', '华北', '华东'], 'amount': [1.0, 2.0, 3.0]})\n"
        "region_stats = orders.group_by('region').agg(pl.col('amount').sum()).sort('region')\n"
        "print('学员自己的输出')\n"
    )
    assertions = [
        {"id": "a1", "type": "expr_true", "expr": "region_stats.height == 2", "title": "区域数应为 2"},
        {"id": "a2", "type": "schema", "var": "region_stats", "columns": ["region", "amount"]},
        {"id": "a3", "type": "expr_true", "expr": "orders.height == 999", "title": "故意失败"},
    ]
    program += render_assertion_source(assertions)

    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", program],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr

    results, clean_stdout = parse_assertion_output(completed.stdout)
    assert [item["status"] for item in results] == ["passed", "passed", "failed"]
    assert "orders.height == 999" in results[2]["actual"]
    assert results[2]["title"] == "故意失败"
    # 学员自己的输出必须原样保留，标记行被剥掉
    assert clean_stdout.strip() == "学员自己的输出"
    assert ASSERTION_MARKER not in clean_stdout


def test_parse_without_marker_is_a_noop():
    results, clean = parse_assertion_output("hello\nworld\n")
    assert results == []
    assert clean == "hello\nworld\n"


# ---------------------------------------------------------------------------
# 紧凑尾巴：M2 要走的路径（现有执行接口对 code 有 5000 字符上限）
# ---------------------------------------------------------------------------

_RUNTIME_SOURCE_PATH = Path(assertion_runtime.__file__).resolve()


def _run_program(program: str, tmp_path):
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", program],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return parse_assertion_output(completed.stdout)


def test_compact_footer_fits_the_execution_code_limit(tmp_path):
    assertions = [
        {"id": "a1", "type": "expr_true", "expr": "orders.height == 3", "title": "3 行"},
        {"id": "a2", "type": "schema", "var": "orders", "columns": ["region"]},
    ]
    program = "import polars as pl\norders = pl.DataFrame({'region': ['华东', '华北', '华南']})\n"

    inline = program + render_assertion_source(assertions)
    compact = program + render_assertion_source(assertions, runtime_path=_RUNTIME_SOURCE_PATH)

    # 内联运行时会撑爆 /playground/execute 的 5000 字符上限，紧凑尾巴不会
    assert len(inline) > 5000
    assert len(compact) < 5000

    results, clean_stdout = _run_program(compact, tmp_path)
    assert [item["status"] for item in results] == ["passed", "passed"]
    assert clean_stdout == ""


def test_both_footer_modes_give_identical_results(tmp_path):
    program = (
        "import polars as pl\n"
        "orders = pl.DataFrame({'region': ['华东', '华北'], 'amount': [1.0, 2.0]})\n"
        "region_stats = orders.group_by('region').agg(pl.col('amount').sum()).sort('region')\n"
    )
    assertions = [
        {"id": "a1", "type": "expr_true", "expr": "orders.height == 2"},
        {"id": "a2", "type": "expr_true", "expr": "orders.height == 3", "title": "故意失败"},
        {"id": "a3", "type": "schema", "var": "region_stats", "columns": ["region", "amount"]},
    ]
    inline, _ = _run_program(program + render_assertion_source(assertions), tmp_path)
    compact, _ = _run_program(
        program + render_assertion_source(assertions, runtime_path=_RUNTIME_SOURCE_PATH),
        tmp_path,
    )
    strip = lambda items: [{k: v for k, v in item.items() if k != "durationMs"} for item in items]
    assert strip(inline) == strip(compact)
    assert [item["status"] for item in compact] == ["passed", "failed", "passed"]