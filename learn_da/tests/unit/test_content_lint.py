"""
Task 1: 练习内容 schema 与 lint 测试

验收标准：
- 三个 exercise 可解析
- 缺字段、未知 validator、重复 ID 和语言不匹配都带文件名失败
- 普通课程仍可加载
"""

import shutil
import textwrap
from pathlib import Path

import pytest

from app.core.content_loader import (
    ContentLintError,
    _parse_exercise,
    lint_content,
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

VALID_EXERCISE_FRONTMATTER = {
    "id": 99,
    "slug": "test-lesson",
    "title": "Test Lesson",
    "category": "python",
    "difficulty": "beginner",
    "exercise": {
        "id": "test-exercise-v1",
        "title": "Test Exercise",
        "language": "python",
        "starter_code": "print('hello')\n",
        "objective": "Print hello",
        "hints": ["use print"],
        "validator": {
            "type": "stdout_exact",
            "expected": "hello",
        },
    },
}


def _write_lesson(tmp_path: Path, filename: str, frontmatter: dict) -> Path:
    """写入一个带 frontmatter 的课程文件"""
    import yaml

    content = "---\n" + yaml.dump(frontmatter, allow_unicode=True) + "---\n\n# Body\n"
    file_path = tmp_path / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


# =====================================================
# _parse_exercise 单元测试
# =====================================================


class TestParseExercise:
    """_parse_exercise 的 fail-closed 行为"""

    def test_no_exercise_returns_none(self):
        """无 exercise 字段 → None（纯内容课程）"""
        result = _parse_exercise({"slug": "foo"}, "foo.md")
        assert result is None

    def test_valid_exercise_parsed(self):
        """合法 exercise 正确解析"""
        result = _parse_exercise(VALID_EXERCISE_FRONTMATTER, "test.md")
        assert result is not None
        assert result["id"] == "test-exercise-v1"
        assert result["language"] == "python"
        assert result["validator"]["type"] == "stdout_exact"
        assert result["validator"]["expected"] == "hello"

    def test_exercise_not_dict_raises(self):
        """exercise 非字典 → ContentLintError"""
        with pytest.raises(ContentLintError, match="必须是字典"):
            _parse_exercise({"exercise": "invalid"}, "bad.md")

    def test_missing_exercise_id_raises(self):
        """exercise.id 缺失 → ContentLintError 带文件名"""
        fm = {"exercise": {"title": "no id", "validator": {"type": "stdout_exact"}}}
        with pytest.raises(ContentLintError, match="bad.md"):
            _parse_exercise(fm, "bad.md")

    def test_unknown_validator_type_raises(self):
        """未知 validator type → ContentLintError"""
        fm = {
            "exercise": {
                "id": "x-v1",
                "language": "python",
                "validator": {"type": "eval_script", "expected": "x"},
            }
        }
        with pytest.raises(ContentLintError, match="eval_script"):
            _parse_exercise(fm, "bad.md")

    def test_disallowed_language_raises(self):
        """不允许的语言 → ContentLintError"""
        fm = {
            "exercise": {
                "id": "x-v1",
                "language": "javascript",
                "validator": {"type": "stdout_exact", "expected": "x"},
            }
        }
        with pytest.raises(ContentLintError, match="javascript"):
            _parse_exercise(fm, "bad.md")

    def test_validator_not_dict_raises(self):
        """validator 非字典 → ContentLintError"""
        fm = {"exercise": {"id": "x-v1", "language": "python", "validator": "bad"}}
        with pytest.raises(ContentLintError, match="非字典"):
            _parse_exercise(fm, "bad.md")

    def test_hints_not_list_raises(self):
        """hints 非列表 → ContentLintError"""
        fm = {
            "exercise": {
                "id": "x-v1",
                "language": "python",
                "hints": "not a list",
                "validator": {"type": "stdout_exact", "expected": "x"},
            }
        }
        with pytest.raises(ContentLintError, match="列表"):
            _parse_exercise(fm, "bad.md")


# =====================================================
# load_lesson_from_file 集成
# =====================================================


class TestLoadLessonWithExercise:
    """课程文件加载时 exercise 解析"""

    def test_valid_exercise_lesson_loads(self, local_tmp):
        """有合法 exercise 的课程正常加载"""
        fp = _write_lesson(local_tmp, "good.md", VALID_EXERCISE_FRONTMATTER)
        lesson = load_lesson_from_file(fp)
        assert lesson is not None
        assert lesson["exercise"]["id"] == "test-exercise-v1"

    def test_invalid_exercise_raises_lint_error(self, local_tmp):
        """exercise 非法时抛出 ContentLintError（fail closed）"""
        fm = dict(VALID_EXERCISE_FRONTMATTER)
        fm["exercise"] = {
            "id": "x",
            "language": "python",
            "validator": {"type": "eval"},
        }
        fp = _write_lesson(local_tmp, "bad.md", fm)
        with pytest.raises(ContentLintError):
            load_lesson_from_file(fp)

    def test_normal_lesson_without_exercise_loads(self, local_tmp):
        """普通课程（无 exercise）仍可加载"""
        fm = {
            "id": 1,
            "slug": "plain",
            "title": "Plain",
            "category": "polars",
            "difficulty": "beginner",
        }
        fp = _write_lesson(local_tmp, "plain.md", fm)
        lesson = load_lesson_from_file(fp)
        assert lesson is not None
        assert lesson["exercise"] is None


# =====================================================
# lint_content 集成测试
# =====================================================


class TestLintContent:
    """lint_content 全目录校验"""

    def test_real_content_passes(self):
        """仓库中三节 tracer 课程通过 lint"""
        errors = lint_content()
        assert errors == [], f"Content lint errors: {errors}"

    def test_duplicate_exercise_id_detected(self, local_tmp):
        """重复 exercise.id 被检出"""
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()

        fm1 = dict(VALID_EXERCISE_FRONTMATTER)
        fm2 = dict(VALID_EXERCISE_FRONTMATTER)
        fm2["slug"] = "test-lesson-2"
        fm2["id"] = 100
        # 相同 exercise id
        _write_lesson(lessons_dir, "01-a.md", fm1)
        _write_lesson(lessons_dir, "02-b.md", fm2)

        errors = lint_content(local_tmp)
        assert any("重复" in e for e in errors)

    def test_unknown_validator_detected(self, local_tmp):
        """未知 validator type 被检出"""
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()

        fm = dict(VALID_EXERCISE_FRONTMATTER)
        fm["exercise"] = {
            "id": "x-v1",
            "language": "python",
            "validator": {"type": "llm_judge", "expected": "x"},
        }
        _write_lesson(lessons_dir, "01-bad.md", fm)

        errors = lint_content(local_tmp)
        assert any("llm_judge" in e for e in errors)

    def test_missing_lessons_dir(self, local_tmp):
        """lessons 目录不存在 → 报错"""
        errors = lint_content(local_tmp)
        assert len(errors) == 1
        assert "not found" in errors[0]


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
        fm = dict(VALID_EXERCISE_FRONTMATTER)
        fm["prerequisites"] = ["does-not-exist"]
        fm["recommended_next"] = ["also-missing"]
        _write_lesson(lessons_dir, "01-a.md", fm)

        errors = lint_content(local_tmp)
        assert any("does-not-exist" in e for e in errors)
        assert any("also-missing" in e for e in errors)

    def test_prerequisite_cycle_detected(self, local_tmp):
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()

        fm1 = dict(VALID_EXERCISE_FRONTMATTER)
        fm1["id"] = 1
        fm1["slug"] = "a"
        fm1["prerequisites"] = ["b"]
        _write_lesson(lessons_dir, "01-a.md", fm1)

        fm2 = dict(VALID_EXERCISE_FRONTMATTER)
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

        fm = dict(VALID_EXERCISE_FRONTMATTER)
        fm["track"] = "unknown_track"
        fm["category"] = "polars"
        _write_lesson(lessons_dir, "01-a.md", fm)

        errors = lint_content(local_tmp)
        assert any("unknown_track" in e for e in errors)

    def test_category_mismatch_with_track_detected(self, local_tmp):
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()
        _write_catalog(
            local_tmp,
            [{"key": "good_track", "topic": "t", "label": "Good", "category": "duckdb"}],
        )

        fm = dict(VALID_EXERCISE_FRONTMATTER)
        fm["track"] = "good_track"
        fm["category"] = "polars"
        _write_lesson(lessons_dir, "01-a.md", fm)

        errors = lint_content(local_tmp)
        assert any("不一致" in e for e in errors)

    def test_valid_track_and_category_pass(self, local_tmp):
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()
        _write_catalog(
            local_tmp,
            [{"key": "good_track", "topic": "t", "label": "Good", "category": "polars"}],
        )

        fm = dict(VALID_EXERCISE_FRONTMATTER)
        fm["track"] = "good_track"
        fm["category"] = "polars"
        _write_lesson(lessons_dir, "01-a.md", fm)

        errors = lint_content(local_tmp)
        assert errors == []

    def test_missing_required_field_detected_with_filename(self, local_tmp):
        lessons_dir = local_tmp / "lessons"
        lessons_dir.mkdir()

        fm = dict(VALID_EXERCISE_FRONTMATTER)
        fm.pop("title")
        _write_lesson(lessons_dir, "01-bad.md", fm)

        errors = lint_content(local_tmp)
        assert any("title" in e and "01-bad.md" in e for e in errors)

