"""预期结果（refs）管线：课程 ref 校验、载荷编码、两种参考结果形态。

对应设计稿 §6 的 ``frame_equal`` / ``sql_rows``：断言不再手抄数值，
而是与 ``content/expected/`` 下由 ``scripts/build_expected.py`` 生成的文件比对。
"""

from __future__ import annotations

import base64
import io
import json

import polars as pl
import pytest

from app.practice.assertions import evaluate_assertions
from app.practice.assertion_runtime import _RefTable, _load_ref
from app.workspace.content import (
    EXPECTED_DIR,
    WorkspaceContentError,
    _resolve_expected_path,
    _safe_expected_path,
    load_workspace,
    refs_payload,
)


def _parquet(df: pl.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.write_parquet(buffer)
    return buffer.getvalue()


def _lesson_with(assertions: list[dict], *, cells: int = 2) -> dict:
    return {
        "slug": "demo",
        "workspace": {
            "datasets": [],
            "cells": [
                {"id": f"c{index + 1}", "kind": "task", "task_id": f"t{index + 1}",
                 "code": f"value_{index + 1} = {index + 1}"}
                for index in range(cells)
            ],
            "tasks": [
                {"id": f"t{index + 1}", "title": f"任务 {index + 1}",
                 "cell": f"c{index + 1}", "objective": "把值算出来",
                 "assertions": assertions if index == 0 else [
                     {"id": f"t{index + 1}-ok", "type": "expr_true",
                      "expr": f"value_{index + 1} == {index + 1}"}
                 ]}
                for index in range(cells)
            ],
        },
    }


class TestRefPathValidation:
    def test_ref_names_are_collected_in_order_without_duplicates(self):
        spec = load_workspace(
            _lesson_with([
                {"id": "a", "type": "frame_equal", "var": "v", "ref": "01-t1-a.parquet"},
                {"id": "b", "type": "frame_equal", "var": "v", "ref": "01-t1-a.parquet"},
                {"id": "c", "type": "sql_rows", "query": "select 1", "ref": "01-t1-b.json"},
            ]),
            require_refs=False,
        )
        assert spec is not None
        assert spec.ref_names() == ("01-t1-a.parquet", "01-t1-b.json")

    def test_lesson_without_refs_has_empty_ref_names(self):
        spec = load_workspace(_lesson_with([
            {"id": "a", "type": "expr_true", "expr": "value_1 == 1"},
        ]))
        assert spec is not None
        assert spec.ref_names() == ()

    @pytest.mark.parametrize(
        "ref",
        ["../outside.parquet", "/abs/outside.parquet", "nested/../../outside.json"],
    )
    def test_ref_must_stay_inside_the_expected_directory(self, ref: str):
        with pytest.raises(WorkspaceContentError) as exc:
            _resolve_expected_path(ref)
        assert "不合法" in str(exc.value)

    @pytest.mark.parametrize("ref", ["ref.csv", "ref.txt", "ref"])
    def test_ref_suffix_is_restricted(self, ref: str):
        with pytest.raises(WorkspaceContentError) as exc:
            _resolve_expected_path(ref)
        assert "必须是" in str(exc.value)

    def test_missing_ref_is_rejected_when_loading_lessons(self):
        with pytest.raises(WorkspaceContentError) as exc:
            load_workspace(_lesson_with([
                {"id": "a", "type": "frame_equal", "var": "v", "ref": "does-not-exist.parquet"},
            ]))
        assert "不存在" in str(exc.value)

    def test_missing_ref_is_allowed_while_generating(self):
        spec = load_workspace(
            _lesson_with([
                {"id": "a", "type": "frame_equal", "var": "v", "ref": "not-yet.parquet"},
            ]),
            require_refs=False,
        )
        assert spec is not None
        assert spec.ref_names() == ("not-yet.parquet",)

    def test_committed_refs_are_readable(self):
        for name in ("02-t2-region-stats.parquet", "07-t2-channels.parquet"):
            assert _safe_expected_path(name).is_file()


class TestRefsPayload:
    def test_payload_is_base64_of_the_file_bytes(self):
        payload = refs_payload(["07-t2-channels.parquet"])
        raw = (EXPECTED_DIR / "07-t2-channels.parquet").read_bytes()
        assert base64.b64decode(payload["07-t2-channels.parquet"]) == raw

    def test_payload_is_cached_and_stable(self):
        first = refs_payload(["07-t2-channels.parquet"])
        second = refs_payload(["07-t2-channels.parquet"])
        assert first == second

    def test_regenerating_a_ref_invalidates_the_cache(self, tmp_path, monkeypatch):
        """build_expected.py 重新生成后，运行中的进程必须立刻用上新字节。"""
        import app.workspace.content as content_module

        target = tmp_path / "regen.parquet"
        target.write_bytes(_parquet(pl.DataFrame({"a": [1.0]})))
        monkeypatch.setattr(content_module, "EXPECTED_DIR", tmp_path)
        content_module._expected_cache.clear()

        first = refs_payload(["regen.parquet"])["regen.parquet"]
        assert base64.b64decode(first) == target.read_bytes()

        # 同进程内替换文件内容 + 改 mtime（模拟重新生成）
        new_bytes = _parquet(pl.DataFrame({"a": [1.0, 2.0]}))
        target.write_bytes(new_bytes)
        import os

        os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 1_000_000))

        second = refs_payload(["regen.parquet"])["regen.parquet"]
        assert base64.b64decode(second) == new_bytes
        assert second != first

    def test_empty_names_give_empty_payload(self):
        assert refs_payload([]) == {}


class TestLoadRef:
    def test_parquet_ref_loads_as_a_frame(self):
        raw = _parquet(pl.DataFrame({"a": [1.0, 2.0]}))
        loaded = _load_ref("r.parquet", {"r.parquet": base64.b64encode(raw).decode()})
        assert isinstance(loaded, pl.DataFrame)
        assert loaded.height == 2

    def test_json_ref_with_columns_keeps_column_names(self):
        body = json.dumps({"columns": ["region", "total"], "rows": [["华东", 10.0]]})
        loaded = _load_ref("r.json", {"r.json": base64.b64encode(body.encode()).decode()})
        assert isinstance(loaded, _RefTable)
        assert loaded.columns == ["region", "total"]
        assert loaded.rows() == [["华东", 10.0]]

    def test_json_ref_without_columns_is_plain_rows(self):
        body = json.dumps({"rows": [["华东", 10.0]]})
        loaded = _load_ref("r.json", {"r.json": base64.b64encode(body.encode()).decode()})
        assert loaded == [["华东", 10.0]]

    def test_missing_ref_raises_key_error(self):
        with pytest.raises(KeyError):
            _load_ref("nope.parquet", {})


class TestFrameEqualAgainstGeneratedRef:
    def test_rows_must_match_the_reference_even_when_shape_is_right(self):
        ref = _parquet(pl.DataFrame({"region": ["华东", "华北"], "revenue": [1.0, 2.0]}))
        spec = [{
            "id": "a", "type": "frame_equal", "var": "stats",
            "ref": "r.parquet", "rtol": 1e-6,
        }]
        good = pl.DataFrame({"region": ["华东", "华北"], "revenue": [1.0, 2.0]})
        assert evaluate_assertions(spec, {"stats": good}, {"r.parquet": ref})[0]["status"] == "passed"

        # 行数、列名都对，只有数值错 —— 旧的 schema + 行数断言会放过这种提交
        bad = pl.DataFrame({"region": ["华东", "华北"], "revenue": [1.0, 2.5]})
        result = evaluate_assertions(spec, {"stats": bad}, {"r.parquet": ref})[0]
        assert result["status"] == "failed"
        assert "2.5" in result["actual"]

    def test_extra_column_in_submission_is_reported(self):
        ref = _parquet(pl.DataFrame({"revenue": [1.0]}))
        spec = [{"id": "a", "type": "frame_equal", "var": "stats", "ref": "r.parquet"}]
        extra = pl.DataFrame({"revenue": [1.0], "note": ["x"]})
        result = evaluate_assertions(spec, {"stats": extra}, {"r.parquet": ref})[0]
        assert result["status"] == "failed"
        assert "多余列" in result["actual"] or "列数不一致" in result["actual"]


class TestSqlRowsAgainstGeneratedRef:
    def test_json_ref_with_columns_compares_row_by_row(self):
        import duckdb

        con = duckdb.connect()
        con.execute("create table orders(region varchar, amount double)")
        con.execute("insert into orders values ('华东', 10.0), ('华北', 20.0)")
        ref = json.dumps({
            "columns": ["region", "total"],
            "rows": [["华东", 10.0], ["华北", 20.0]],
        }).encode()
        spec = [{
            "id": "a", "type": "sql_rows", "ref": "r.json", "connection": "con",
            "query": "select region, sum(amount) as total from orders group by 1 order by 1",
        }]
        assert evaluate_assertions(spec, {"con": con}, {"r.json": ref})[0]["status"] == "passed"

        wrong = json.dumps({"columns": ["region", "total"], "rows": [["华东", 99.0]]}).encode()
        result = evaluate_assertions(spec, {"con": con}, {"r.json": wrong})[0]
        assert result["status"] == "failed"
