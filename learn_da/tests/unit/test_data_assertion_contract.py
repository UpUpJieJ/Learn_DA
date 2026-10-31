"""Data-course checks must compare structured observations, not learner expressions."""

from pathlib import Path

import yaml


def test_data_courses_have_no_free_expression_assertions():
    root = Path(__file__).resolve().parents[2] / "content" / "lessons"
    remaining = []
    for path in sorted(root.glob("*.md")):
        frontmatter = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
        for task in frontmatter["workspace"]["tasks"]:
            for assertion in task["assertions"]:
                if assertion["type"] == "expr_true":
                    remaining.append(f"{path.name}/{assertion['id']}")
    assert not remaining, f"Free expressions remain in data courses: {remaining}"


def test_unordered_reference_bytes_are_deterministic():
    import polars as pl

    from scripts.build_expected import _dump_frame_equal

    frame = pl.DataFrame({"id": [2, 1], "amount": [20.0, 10.0]})
    assert _dump_frame_equal(frame, order_matters=False) == _dump_frame_equal(
        frame.reverse(), order_matters=False
    )
    assert _dump_frame_equal(frame, order_matters=True) != _dump_frame_equal(
        frame.reverse(), order_matters=True
    )


def test_workspace_loader_rejects_free_expressions_before_runtime():
    import pytest
    from app.workspace.content import load_workspace, WorkspaceContentError
    from tests.unit.test_workspace_refs import _lesson_with
    with pytest.raises(WorkspaceContentError, match="expr_true"):
        load_workspace(_lesson_with([{"id":"a", "type":"expr_true", "expr":"value_1 == 1"}]))
