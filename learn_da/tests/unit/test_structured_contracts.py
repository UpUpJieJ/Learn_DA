import base64
import json

import pytest

from app.practice.assertions import validate_assertions
from app.practice.assertion_runtime import run


def test_fixed_input_call_rejects_custom_equality():
    class AlwaysEqual:
        def __eq__(self, other):
            return True
    spec = validate_assertions([dict(id="a", type="call", function="bonus", args=[95], expect=100)])
    assert run({"bonus": lambda n: AlwaysEqual()}, spec)[0]["status"] == "error"
    assert run({"bonus": lambda n: n + 5}, spec)[0]["status"] == "passed"
    assert run({"bonus": lambda n: 0}, spec)[0]["status"] == "failed"


def test_legacy_expression_rejects_custom_objects_before_comparison():
    class Always:
        def __eq__(self, other): return True
    spec = validate_assertions([dict(id="a", type="expr_true", expr="x == 100")])
    assert run({"x": Always()}, spec)[0]["status"] == "error"


def test_value_contract_preserves_container_types_and_numeric_tolerance():
    spec = validate_assertions([dict(id="a", type="value", var="result", expect={"a": [1, 2.0]})])
    assert run({"result": {"a": [1, 2.0000001]}}, spec)[0]["status"] == "passed"
    assert run({"result": {"a": [True, 2]}}, spec)[0]["status"] == "failed"


def test_sql_extra_columns_are_not_ignored():
    class Cursor:
        def execute(self, query): return self
        def fetchall(self): return [[1, 999]]
    spec = validate_assertions([dict(id="a", type="sql_rows", query="select 1", ref="r")])
    refs = {"r": base64.b64encode(json.dumps([[1]]).encode()).decode()}
    assert run({"con": Cursor()}, spec, refs)[0]["status"] == "failed"


def test_empty_sql_result_still_checks_column_count():
    class Cursor:
        description = [("x",), ("extra",)]
        def execute(self, query): return self
        def fetchall(self): return []
    spec = validate_assertions([dict(id="a", type="sql_rows", query="select 1", ref="r")])
    refs = {"r": base64.b64encode(json.dumps({"columns": ["x"], "rows": []}).encode()).decode()}
    assert run({"con": Cursor()}, spec, refs)[0]["status"] == "failed"


def test_unordered_frame_still_enforces_requested_sort_and_allows_ties():
    import polars as pl
    spec = validate_assertions([dict(id="a", type="frame_equal", var="df", ref="r",
                                    order_matters=False, sorted_by=["amount"], descending=True)])
    refs = {"r": base64.b64encode(json.dumps({"columns":["amount"],"rows":[[30],[30],[10]]}).encode()).decode()}
    assert run({"df":pl.DataFrame({"amount":[30,30,10]})}, spec, refs)[0]["status"] == "passed"
    assert run({"df":pl.DataFrame({"amount":[30,10,30]})}, spec, refs)[0]["status"] == "failed"


def test_table_numeric_cells_do_not_coerce_strings_and_nan_matches_nan():
    import io, polars as pl
    from app.practice.assertions import evaluate_assertions
    spec = [dict(id="a", type="frame_equal", var="df", ref="r")]
    buf = io.BytesIO(); pl.DataFrame({"x":[1.0]}).write_parquet(buf)
    assert evaluate_assertions(spec, {"df":pl.DataFrame({"x":["1"]})}, {"r":buf.getvalue()})[0]["status"] == "failed"
    buf = io.BytesIO(); pl.DataFrame({"x":[float('nan')]}).write_parquet(buf)
    assert evaluate_assertions(spec, {"df":pl.DataFrame({"x":[float('nan')]})}, {"r":buf.getvalue()})[0]["status"] == "passed"


def test_near_zero_values_have_a_small_absolute_tolerance():
    spec=validate_assertions([dict(id="a",type="value",var="x",expect=0.0)])
    assert run({"x":1e-10},spec)[0]["status"] == "passed"


def test_infinite_numeric_values_require_same_sign_and_value():
    from app.practice.assertion_runtime import _numeric_equal
    assert not _numeric_equal(0.0, float('inf'), 1e-6, 0)
    assert not _numeric_equal(float('-inf'), float('inf'), 1e-6, 0)
    assert _numeric_equal(float('inf'), float('inf'), 1e-6, 0)


def test_sql_reference_column_names_are_checked():
    class Cursor:
        description=[("wrong_alias",)]
        def execute(self, query): return self
        def fetchall(self): return [[1]]
    spec=validate_assertions([dict(id="a", type="sql_rows", query="select 1 as expected", ref="r")])
    refs={"r":base64.b64encode(json.dumps({"columns":["expected"],"rows":[[1]]}).encode()).decode()}
    assert run({"con":Cursor()}, spec, refs)[0]["status"] == "failed"


@pytest.mark.parametrize("spec", [
    dict(type="call", function="f.__call__", args=[], expect=1),
    dict(type="call", function="f", args="not-list", expect=1),
    dict(type="value", var="x", comparison="eval", expect=1),
])
def test_malformed_structured_contract_is_rejected(spec):
    with pytest.raises(ValueError):
        validate_assertions([dict(id="a", **spec)])
