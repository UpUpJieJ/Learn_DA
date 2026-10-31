from pathlib import Path

import pytest

from app.core.content_loader import lint_content, load_lesson_from_file


def test_old_practice_metadata_is_absent_from_current_courses():
    import yaml
    root = Path(__file__).resolve().parents[2] / "content/lessons"
    for path in root.glob("*.md"):
        frontmatter = yaml.safe_load(path.read_text(encoding="utf-8").split("---",2)[1])
        assert "practice_objective" not in frontmatter
        assert "completion_criteria" not in frontmatter
        lesson = load_lesson_from_file(path)
        assert "practice_objective" not in lesson
        assert "completion_criteria" not in lesson


def test_relative_default_content_path_still_runs_workspace_lint(monkeypatch):
    import app.core.content_loader as module
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    monkeypatch.setattr(module, "_lint_workspaces", lambda path: ["workspace guard executed"])
    assert "workspace guard executed" in lint_content(Path("content"))


def test_orphan_reference_is_reported(tmp_path):
    from scripts.build_expected import orphan_references
    (tmp_path / "orphan.parquet").write_bytes(b"unused")
    (tmp_path / "used.json").write_text("[]")
    assert orphan_references({"used.json"}, tmp_path) == ["orphan.parquet"]
