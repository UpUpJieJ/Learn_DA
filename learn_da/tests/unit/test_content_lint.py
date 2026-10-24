"""
课程内容 schema 与 lint 测试

验收标准：
- 普通课程可加载
- frontmatter / catalog 损坏时 fail closed（显式报错，不静默跳过）
- 引用图（前置课、track）错误被检出
"""

import shutil
import textwrap
from pathlib import Path

import pytest

from app.core.content_loader import (
    ContentLintError,
    lint_content,
    load_catalog,
    load_lesson_from_file,
    parse_frontmatter,
)

# Windows 下 tmp_path 可能有权限问题，使用项目内临时目录
_LOCAL_TMP = Path(__file__).parent.parent.parent / ".pytest_tmp"


@pytest.fixture()
def local_tmp():
    """每个测试函数独立的临时目录"""
    import uuid

    d = _LOCAL_TMP / uuid.uuid4().hex[:12]
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


# =====================================================
# Fixtures: 临时课程内容
# =====================================================

VALID_LESSON_FRONTMATTER = {
    "id": 99,
    "slug": "test-lesson",
    "title": "Test Lesson",
    "category": "python",
    "difficulty": "beginner",
}


def _write_lesson(tmp_path: Path, filename: str, frontmatter: dict) -> Path:
    """写入一个带 frontmatter 的课程文件"""
    import yaml

    content = "---\n" + yaml.dump(frontmatter, allow_unicode=True) + "---\n\n# Body\n"
    file_path = tmp_path / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


# =====================================================
# load_lesson_from_file 集成
# =====================================================


class TestLoadLesson:
    """课程文件加载"""

    def test_plain_lesson_loads(self, local_tmp):
        """普通课程可加载"""
        fp = _write_lesson(local_tmp, "plain.md", VALID_LESSON_FRONTMATTER)
        lesson = load_lesson_from_file(fp)
        assert lesson is not None
        assert lesson["slug"] == "test-lesson"

    def test_legacy_exercise_block_is_ignored(self, local_tmp):
        """旧练习链路的 exercise 块已下线：残留字段不再被解析，也不阻断加载"""
        fm = dict(VALID_LESSON_FRONTMATTER)
        fm["exercise"] = {
            "id": "test-exercise-v1",
            "validator": {"type": "stdout_exact", "expected": "hello"},
        }
        fp = _write_lesson(local_tmp, "legacy.md", fm)
        lesson = load_lesson_from_file(fp)
        assert lesson is not None
        assert "exercise" not in lesson

    def test_workspace_block_is_carried(self, local_tmp):
        """workspace 块被带进 lesson dict（前端据此给工作区入口）"""
        fm = dict(VALID_LESSON_FRONTMATTER)
        fm["workspace"] = {"cells": [], "tasks": []}
        fp = _write_lesson(local_tmp, "ws.md", fm)
        lesson = load_lesson_from_file(fp)
        assert lesson is not None
        assert lesson["workspace"] == {"cells": [], "tasks": []}


# =====================================================
# lint_content 集成测试
# =====================================================


class TestLintContent:
    """lint_content 全目录校验"""

    def test_real_content_passes(self):
        """仓库内容通过 lint"""
        errors = lint_content()
        assert errors == [], f"Content lint errors: {errors}"

    def test_duplicate_slug_detected(self, local_tmp):
        """重复 slug 被检出"""
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()

        fm1 = dict(VALID_LESSON_FRONTMATTER)
        fm2 = dict(VALID_LESSON_FRONTMATTER)
        fm2["id"] = 100
        _write_lesson(lessons_dir, "01-a.md", fm1)
        _write_lesson(lessons_dir, "02-b.md", fm2)

        errors = lint_content(local_tmp)
        assert any("重复" in e for e in errors)

    def test_missing_lessons_dir(self, local_tmp):
        """lessons 目录不存在 → 报错"""
        errors = lint_content(local_tmp)
        assert len(errors) == 1
        assert "not found" in errors[0]


# =====================================================
# frontmatter / catalog 解析 fail-closed
# （YAML 损坏必须显式报错，不得静默跳过导致缺课）
# =====================================================

_BROKEN_YAML_LESSON = '---\nid: 1\nslug: broken\ntitle: "unclosed quote\n---\n\n# Body\n'


class TestFrontmatterFailClosed:
    """frontmatter 缺失或 YAML 损坏的 fail-closed 行为"""

    def test_yaml_syntax_error_detected_by_lint(self, local_tmp):
        """frontmatter YAML 语法错误 → lint 报错（而非跳过该文件）"""
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()
        (lessons_dir / "01-broken.md").write_text(
            _BROKEN_YAML_LESSON, encoding="utf-8"
        )

        errors = lint_content(local_tmp)
        assert any("01-broken.md" in e and "YAML" in e for e in errors)

    def test_missing_frontmatter_detected_by_lint(self, local_tmp):
        """无 frontmatter 分隔块的文件 → lint 报错（而非跳过）"""
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()
        (lessons_dir / "02-plain.md").write_text(
            "# Just markdown\n", encoding="utf-8"
        )

        errors = lint_content(local_tmp)
        assert any("02-plain.md" in e and "缺少 frontmatter" in e for e in errors)

    def test_non_mapping_frontmatter_detected_by_lint(self, local_tmp):
        """frontmatter 根节点非映射（如列表）→ lint 报错"""
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()
        (lessons_dir / "03-list.md").write_text(
            "---\n- just\n- a list\n---\n\n# Body\n", encoding="utf-8"
        )

        errors = lint_content(local_tmp)
        assert any("03-list.md" in e and "YAML" in e for e in errors)

    def test_yaml_syntax_error_raises_on_load(self, local_tmp):
        """YAML 语法错误 → load_lesson_from_file 抛 ContentLintError（而非返回 None）"""
        fp = local_tmp / "broken.md"
        fp.write_text(_BROKEN_YAML_LESSON, encoding="utf-8")
        with pytest.raises(ContentLintError, match="YAML"):
            load_lesson_from_file(fp)

    def test_missing_frontmatter_raises_on_load(self, local_tmp):
        """无 frontmatter → load_lesson_from_file 抛 ContentLintError（而非返回 None）"""
        fp = local_tmp / "plain.md"
        fp.write_text("# Just markdown\n", encoding="utf-8")
        with pytest.raises(ContentLintError, match="缺少 frontmatter"):
            load_lesson_from_file(fp)


class TestCatalogFailClosed:
    """catalog.yml 损坏必须显式报错，不得静默禁用一致性校验"""

    def test_corrupt_catalog_yaml_detected(self, local_tmp):
        """catalog.yml YAML 语法错误 → lint 报错"""
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()
        (local_tmp / "catalog.yml").write_text(
            "tracks: [unclosed\n", encoding="utf-8"
        )

        errors = lint_content(local_tmp)
        assert any("catalog.yml" in e and "YAML" in e for e in errors)

    def test_invalid_catalog_schema_detected(self, local_tmp):
        """catalog.yml schema 非法 → lint 报错"""
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()
        (local_tmp / "catalog.yml").write_text("tracks: 42\n", encoding="utf-8")

        errors = lint_content(local_tmp)
        assert any("catalog.yml" in e for e in errors)

    def test_load_catalog_corrupt_raises(self, local_tmp):
        """load_catalog 对损坏的 catalog.yml 抛 ContentLintError"""
        (local_tmp / "catalog.yml").write_text(
            "platform: [unclosed\n", encoding="utf-8"
        )
        with pytest.raises(ContentLintError, match="catalog.yml"):
            load_catalog(local_tmp)


def _write_catalog(tmp_path: Path, tracks: list[dict]) -> None:
    """写入 catalog.yml（用于 track/category 一致性校验）"""
    import yaml

    catalog = {"platform": {"name": "T"}, "topics": [], "tracks": tracks}
    (tmp_path / "catalog.yml").write_text(
        yaml.dump(catalog, allow_unicode=True), encoding="utf-8"
    )


class TestLintReferenceGraph:
    """引用图与 catalog 一致性校验"""

    def test_reference_to_missing_lesson_detected(self, local_tmp):
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()
        fm = dict(VALID_LESSON_FRONTMATTER)
        fm["prerequisites"] = ["does-not-exist"]
        fm["recommended_next"] = ["also-missing"]
        _write_lesson(lessons_dir, "01-a.md", fm)

        errors = lint_content(local_tmp)
        assert any("does-not-exist" in e for e in errors)
        assert any("also-missing" in e for e in errors)

    def test_prerequisite_cycle_detected(self, local_tmp):
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()

        fm1 = dict(VALID_LESSON_FRONTMATTER)
        fm1["id"] = 1
        fm1["slug"] = "a"
        fm1["prerequisites"] = ["b"]
        _write_lesson(lessons_dir, "01-a.md", fm1)

        fm2 = dict(VALID_LESSON_FRONTMATTER)
        fm2["id"] = 2
        fm2["slug"] = "b"
        fm2["prerequisites"] = ["a"]
        _write_lesson(lessons_dir, "02-b.md", fm2)

        errors = lint_content(local_tmp)
        assert any("环" in e for e in errors)

    def test_track_not_in_catalog_detected(self, local_tmp):
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()
        _write_catalog(
            local_tmp,
            [{"key": "good_track", "topic": "t", "label": "Good", "category": "polars"}],
        )

        fm = dict(VALID_LESSON_FRONTMATTER)
        fm["track"] = "unknown_track"
        fm["category"] = "polars"
        _write_lesson(lessons_dir, "01-a.md", fm)

        errors = lint_content(local_tmp)
        assert any("unknown_track" in e for e in errors)
