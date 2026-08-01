"""阶段 4 Task 1：内容索引（Content Catalog 深模块）测试。

覆盖：
- 真实内容可构建索引，且版本哈希稳定、随内容变化；
- lint 失败时构建索引 fail closed（抛出而非静默跳过）；
- 进程级单例与重置；
- LearningRepository 复用共享索引，不再各自扫描文件系统。
"""

import shutil
import uuid
from pathlib import Path

import pytest

from app.core import content_catalog
from app.core.content_catalog import (
    build_content_index,
    get_content_index,
    reset_content_index,
)
from app.core.content_schemas import ContentLintError

_LOCAL_TMP = Path(__file__).parent.parent.parent / ".pytest_tmp"


@pytest.fixture()
def local_tmp():
    d = _LOCAL_TMP / uuid.uuid4().hex[:12]
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _write_lesson(tmp_path: Path, filename: str, frontmatter: dict) -> Path:
    import yaml

    content = "---\n" + yaml.dump(frontmatter, allow_unicode=True) + "---\n\n# Body\n"
    fp = tmp_path / filename
    fp.write_text(content, encoding="utf-8")
    return fp


def _make_content_dir(tmp_path: Path) -> Path:
    content_dir = tmp_path / "content"
    (content_dir / "lessons").mkdir(parents=True)
    (content_dir / "examples").mkdir(parents=True)
    (content_dir / "catalog.yml").write_text(
        "platform:\n  name: T\n  title: T\ntopics: []\ntracks: []\n",
        encoding="utf-8",
    )
    fm = {
        "id": 1,
        "slug": "a",
        "title": "A",
        "category": "polars",
        "difficulty": "beginner",
        "track": "",
        "prerequisites": [],
        "recommended_next": [],
    }
    _write_lesson(content_dir / "lessons", "01-a.md", fm)
    return content_dir


class TestBuildContentIndex:
    def test_real_content_builds(self):
        """真实内容目录可构建索引，课程/示例/catalog 均可用。"""
        index = build_content_index()
        assert len(index.lessons) >= 13
        assert len(index.examples) >= 4
        assert index.catalog["platform"]["name"] == "Learn DA"
        assert len(index.catalog["tracks"]) >= 4
        assert index.content_version

    def test_version_stable_across_builds(self, local_tmp):
        content_dir = _make_content_dir(local_tmp)
        v1 = build_content_index(content_dir).content_version
        v2 = build_content_index(content_dir).content_version
        assert v1 == v2

    def test_version_changes_with_content(self, local_tmp):
        content_dir = _make_content_dir(local_tmp)
        before = build_content_index(content_dir).content_version
        _write_lesson(
            content_dir / "lessons",
            "02-b.md",
            {
                "id": 2,
                "slug": "b",
                "title": "B",
                "category": "polars",
                "difficulty": "beginner",
                "track": "",
                "prerequisites": [],
                "recommended_next": [],
            },
        )
        after = build_content_index(content_dir).content_version
        assert before != after

    def test_lint_error_fails_closed(self, local_tmp):
        """lint 失败时 build_content_index 抛出，而不是静默跳过。"""
        content_dir = _make_content_dir(local_tmp)
        fm = {
            "id": 2,
            "slug": "b",
            "title": "B",
            "category": "polars",
            "difficulty": "beginner",
            "prerequisites": ["missing-lesson"],
        }
        _write_lesson(content_dir / "lessons", "02-b.md", fm)

        with pytest.raises(ContentLintError, match="missing-lesson"):
            build_content_index(content_dir)


class TestSharedIndex:
    def test_get_content_index_is_singleton(self):
        reset_content_index()
        first = get_content_index()
        second = get_content_index()
        assert first is second
        assert len(first.lessons) >= 13

    def test_reset_content_index(self):
        reset_content_index()
        first = get_content_index()
        reset_content_index()
        second = get_content_index()
        assert first is not second
        reset_content_index()

    def test_learning_repository_uses_shared_index(self, monkeypatch):
        """LearningRepository 消费共享索引，不再扫描文件系统。"""
        from app.learning.repository import LearningRepository

        reset_content_index()
        loaded = {}

        original = content_catalog.build_content_index

        def spy_build(content_dir=None):
            if "count" not in loaded:
                loaded["count"] = 0
            loaded["count"] += 1
            return original(content_dir)

        monkeypatch.setattr(content_catalog, "build_content_index", spy_build)

        repo_a = LearningRepository()
        repo_b = LearningRepository()
        assert repo_a._index is repo_b._index
        assert len(repo_a.list_lessons()) >= 13
        # 共享索引只构建一次，两个 repository 实例不再各自扫描
        assert loaded["count"] == 1
        reset_content_index()
