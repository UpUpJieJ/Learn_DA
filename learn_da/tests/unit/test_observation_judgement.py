import pytest

from app.practice.observations import judge_observations, observation_request


def request():
    return {"requestId": "r", "cells": [{"cellId": "c1", "code": "x=1"}],
            "refs": {"secret": "hidden"}, "runtime": "secret source",
            "assertions": [{"id": "a", "type": "value", "var": "x", "expect": 2}]}


def response(value=1):
    return {"status": "success", "verdict": "passed", "executedUpto": "c1",
            "cells": [{"cellId": "c1", "status": "success"}],
            "observations": [{"t": "vars", "vars": {"x": {"kind": "json", "data": str(value)}}}]}


def test_outbound_request_never_contains_expected_material():
    payload = observation_request(request())
    assert payload["observationMode"] is True
    assert "refs" not in payload and "runtime" not in payload
    assert payload["assertions"] == [{"id": "a", "type": "value", "var": "x"}]


def test_forged_verdict_does_not_override_backend_comparison():
    assert judge_observations(request(), response(1))["verdict"] == "assertion_failed"
    assert judge_observations(request(), response(2))["verdict"] == "passed"


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(observations=[]),
    lambda r: r.update(cells=[]),
    lambda r: r.update(executedUpto=None),
    lambda r: r.update(status="timeout"),
])
def test_incomplete_runner_results_fail_closed(mutate):
    result = response(2)
    mutate(result)
    assert judge_observations(request(), result)["verdict"] != "passed"


def test_call_compares_concrete_observation_without_executing_function_in_backend():
    req = request()
    req["assertions"] = [{"id": "a", "type": "call", "function": "bonus", "args": [95], "expect": 100}]
    res = response()
    res["observations"] = [{"t": "call", "id": "a", "value": {"kind": "json", "data": "100"}}]
    assert judge_observations(req, res)["verdict"] == "passed"


@pytest.mark.parametrize("cells", [
    [{"cellId": "c1", "status": "success"}, {"cellId": "c1", "status": "error"}],
    [{"cellId": "c1", "status": "success"}, {"cellId": "unknown", "status": "error"}],
])
def test_duplicate_or_extra_cell_results_fail_closed(cells):
    result = response(2)
    result["cells"] = cells
    assert judge_observations(request(), result)["verdict"] == "execution_failed"


def test_bounded_json_table_is_judged_without_parsing_untrusted_binary():
    import base64, json
    req = request()
    req["assertions"] = [dict(id="a", type="frame_equal", var="x", ref="r")]
    req["refs"] = {"r": base64.b64encode(json.dumps({"columns":["x"],"rows":[[1]]}).encode()).decode()}
    result = response()
    result["observations"] = [{"t":"vars", "vars":{"x":{"kind":"table", "columns":["x"],"rows":[[1]],"dtypes":{"x":"Int64"}}}}]
    assert judge_observations(req, result)["verdict"] == "passed"


def test_sql_tagged_date_matches_generated_json_reference():
    import base64, json
    req = request()
    req["assertions"] = [dict(id="a", type="sql_rows", query="select d", ref="r")]
    req["refs"] = {"r": base64.b64encode(json.dumps([["2025-01-01"]]).encode()).decode()}
    result = response()
    result["observations"] = [{"t":"rows", "id":"a", "rows":[[{"__d__":"2025-01-01"}]]}]
    assert judge_observations(req, result)["verdict"] == "passed"


def test_untrusted_binary_is_never_decoded_in_backend(monkeypatch):
    import polars as pl
    def forbidden(*args, **kwargs):
        raise AssertionError("untrusted IPC must not reach the native decoder")
    monkeypatch.setattr(pl, "read_ipc", forbidden)
    res = response(2)
    res["observations"] = [{"t": "vars", "vars": {"x": {"kind": "arrow", "data": "AAAA"}}}]
    assert judge_observations(request(), res)["assertions"][0]["status"] == "error"


@pytest.mark.parametrize("bad", [
    {"columns": ["x", "x"], "rows": [[1, 2]], "dtypes": {"x": "Int64"}},
    {"columns": ["x"], "rows": [[1, 2]], "dtypes": {"x": "Int64"}},
    {"columns": ["x"], "rows": [[1]], "dtypes": {"x": 123}},
    {"columns": ["x"], "rows": [[{"__unknown__": "x"}]], "dtypes": {"x": "String"}},
])
def test_malformed_table_is_rejected(bad):
    res = response(2)
    res["observations"] = [{"t": "vars", "vars": {"x": dict(kind="table", **bad)}}]
    assert judge_observations(request(), res)["verdict"] != "passed"


def test_schema_does_not_trust_declared_dtype_for_invalid_values():
    req = request()
    req["assertions"] = [dict(id="a", type="schema", var="x", dtypes={"amount":"Float64"})]
    res = response()
    res["observations"] = [{"t":"vars", "vars":{"x":{"kind":"table", "columns":["amount"],
        "rows":[["not a number"]], "dtypes":{"amount":"Float64"}}}}]
    assert judge_observations(req, res)["verdict"] != "passed"


def test_sql_requires_each_row_to_be_a_list():
    import base64, json
    req = request()
    req["assertions"] = [dict(id="a", type="sql_rows", query="select 1", ref="r")]
    req["refs"] = {"r": base64.b64encode(json.dumps([[1]]).encode()).decode()}
    res = response()
    res["observations"] = [{"t":"rows", "id":"a", "rows":["1"]}]
    assert judge_observations(req, res)["verdict"] != "passed"


def test_decimal38_keeps_all_digits_without_default_decimal_context_rounding():
    from decimal import Decimal
    import polars as pl
    df=pl.DataFrame({"v":[Decimal('9'*38)]}, schema={"v":pl.Decimal(38,0)})
    dtype=str(df.schema['v'])
    req=request();req['assertions']=[dict(id='a',type='schema',var='x',dtypes={'v':dtype})]
    res=response();res['observations']=[{'t':'vars','vars':{'x':{'kind':'table','columns':['v'],
        'dtypes':{'v':dtype},'rows':[[{'__dec__':str(df.item())}]]}}}]
    assert judge_observations(req,res)['verdict']=='passed'


def test_float32_metadata_cannot_claim_an_unrepresentable_value():
    req=request();req['assertions']=[dict(id='a',type='schema',var='x',dtypes={'v':'Float32'})]
    res=response();res['observations']=[{'t':'vars','vars':{'x':{'kind':'table','columns':['v'],
        'dtypes':{'v':'Float32'},'rows':[[1e300]]}}}]
    assert judge_observations(req,res)['verdict']!='passed'
