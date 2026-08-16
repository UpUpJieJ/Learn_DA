"""
内容加载器：从 Markdown 文件加载课程和示例
"""

import re
from pathlib import Path
from typing import Any

import yaml

from .content_schemas import (
    ContentLintError,
    ContentCatalog,
    validate_lesson_frontmatter,
)

# Phase 2: 可验证练习判定器白名单
ALLOWED_VALIDATOR_TYPES = frozenset(
    {"stdout_exact", "stdout_contains", "dataframe_rows"}
)
ALLOWED_EXERCISE_LANGUAGES = frozenset({"python", "sql"})


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    解析 Markdown 文件的 frontmatter

    格式：
    ---
    key: value
    ---

    返回: (frontmatter_dict, markdown_body)
    """
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return {}, content

    frontmatter_text = match.group(1)
    body = match.group(2)

    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, body.strip()


def extract_code_example(content: str) -> str | None:
    """
    从 Markdown 内容中提取标记为 example 的代码块

    格式：
    ```python:example
    code here
    ```
    """
    pattern = r"```python:example\s*\n(.*?)\n```"
    match = re.search(pattern, content, re.DOTALL)

    if match:
        return match.group(1).strip()
    return None


def load_lesson_from_file(file_path: Path) -> dict[str, Any] | None:
    """
    从单个 Markdown 文件加载课程
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(content)

        if not frontmatter:
            return None

        # 提取代码示例
        code_example = extract_code_example(content)

        # Phase 2: 解析并校验练习定义
        exercise = _parse_exercise(frontmatter, file_path.name)

        lesson = {
            "id": frontmatter.get("id"),
            "slug": frontmatter.get("slug"),
            "title": frontmatter.get("title"),
            "topic": frontmatter.get("topic", "data-analysis"),
            "category": frontmatter.get("category"),
            "difficulty": frontmatter.get("difficulty"),
            "description": frontmatter.get("description", ""),
            "estimated_minutes": frontmatter.get("estimated_minutes", 15),
            "order": frontmatter.get("order", 0),
            "tags": frontmatter.get("tags", []),
            "content": body,
            "code_example": code_example or "",
            "prev_lesson": frontmatter.get("prev_lesson"),
            "next_lesson": frontmatter.get("next_lesson"),
            # Phase 2: 练习结构字段（可选）
            "practice_objective": frontmatter.get("practice_objective", ""),
            "completion_criteria": frontmatter.get("completion_criteria", []),
            # Phase 2: 正式练习定义
            "exercise": exercise,
            # Phase 3: 建议系统元数据（可选）
            "track": frontmatter.get("track", ""),
            "prerequisites": frontmatter.get("prerequisites", []),
            "recommended_next": frontmatter.get("recommended_next", []),
            "skill_tags": frontmatter.get("skill_tags", []),
            "is_review_friendly": frontmatter.get("is_review_friendly", False),
            "is_branch_point": frontmatter.get("is_branch_point", False),
            # 关联示例（slug 列表，引用必须存在于 content/examples）
            "examples": frontmatter.get("examples", []),
        }

        # 验证必需字段（fail closed：缺失即报错，不再静默跳过）
        required_fields = ["id", "slug", "title", "category", "difficulty"]
        for field in required_fields:
            if lesson.get(field) is None:
                raise ContentLintError(f"缺少必需字段 '{field}'", file_path.name)

        # Pydantic schema 校验（字段级错误）
        validate_lesson_frontmatter(frontmatter, file_path.name)

        return lesson

    except ContentLintError:
        raise
    except Exception as e:
        print(f"[ContentLoader] Error loading {file_path}: {e}")
        return None


def _parse_exercise(
    frontmatter: dict[str, Any], file_name: str
) -> dict[str, Any] | None:
    """解析并校验 frontmatter 中的 exercise 字段。

    fail closed：有 exercise 但非法 → 抛出 ContentLintError。
    无 exercise → 返回 None（纯内容课程）。
    """
    raw = frontmatter.get("exercise")
    if raw is None:
        return None

    if not isinstance(raw, dict):
        raise ContentLintError("exercise 必须是字典", file_name)

    # 必填字段
    exercise_id = raw.get("id")
    if not exercise_id or not isinstance(exercise_id, str):
        raise ContentLintError("exercise.id 缺失或非字符串", file_name)

    title = raw.get("title", "")
    language = raw.get("language", "python")
    if language not in ALLOWED_EXERCISE_LANGUAGES:
        raise ContentLintError(
            f"exercise.language '{language}' 不在允许列表中: {sorted(ALLOWED_EXERCISE_LANGUAGES)}",
            file_name,
        )

    starter_code = raw.get("starter_code", "")
    objective = raw.get("objective", "")
    hints = raw.get("hints", [])
    if not isinstance(hints, list):
        raise ContentLintError("exercise.hints 必须是列表", file_name)

    validator_raw = raw.get("validator")
    if not isinstance(validator_raw, dict):
        raise ContentLintError("exercise.validator 缺失或非字典", file_name)

    validator_type = validator_raw.get("type", "")
    if validator_type not in ALLOWED_VALIDATOR_TYPES:
        raise ContentLintError(
            f"exercise.validator.type '{validator_type}' 不在允许列表中: {sorted(ALLOWED_VALIDATOR_TYPES)}",
            file_name,
        )

    return {
        "id": exercise_id,
        "title": title,
        "language": language,
        "starter_code": starter_code,
        "objective": objective,
        "hints": hints,
        "validator": {
            "type": validator_type,
            "expected": validator_raw.get("expected"),
        },
    }


def lint_content(content_dir: Path | None = None) -> list[str]:
    """校验所有内容的合法性。

    返回错误列表；空列表表示全部通过。错误格式 ``[file:field] message``。
    校验项：
    - 有 exercise 的课程必须完整合法
    - exercise.id 不能重复
    - 语言必须在允许列表
    - validator type 必须在白名单
    - track 必须存在于 catalog（catalog.yml 存在时）
    - category 必须与 track.category 一致（catalog.yml 存在时）
    - prerequisite / recommended_next 引用必须存在
    - prerequisites 课程图必须无环
    - examples 引用的示例必须存在
    """
    if content_dir is None:
        content_dir = Path(__file__).parent.parent.parent / "content"

    errors: list[str] = []
    lessons_dir = content_dir / "lessons"
    if not lessons_dir.exists():
        return [f"Lessons directory not found: {lessons_dir}"]

    seen_exercise_ids: set[str] = set()
    seen_slugs: set[str] = set()
    lessons: dict[str, dict[str, Any]] = {}

    # 目录级问题检查优先于单文件字段级问题。
    catalog = _load_catalog_safely(content_dir)
    track_by_key = {t["key"]: t for t in catalog.get("tracks", [])}

    for md_file in sorted(lessons_dir.glob("*.md")):
        file_name = md_file.name
        try:
            content = md_file.read_text(encoding="utf-8")
            frontmatter, _body = parse_frontmatter(content)

            if not frontmatter:
                continue

            # 字段级 schema 校验（缺字段 / 类型错误都带文件名报出）
            try:
                validate_lesson_frontmatter(frontmatter, file_name)
            except ContentLintError as e:
                errors.append(str(e))

            slug = frontmatter.get("slug")
            if slug:
                if slug in seen_slugs:
                    errors.append(f"[{file_name}:slug] slug '{slug}' 重复")
                seen_slugs.add(slug)

            # 有 exercise 字段时强制校验
            if "exercise" in frontmatter:
                try:
                    exercise = _parse_exercise(frontmatter, file_name)
                    if exercise:
                        eid = exercise["id"]
                        if eid in seen_exercise_ids:
                            errors.append(
                                f"[{file_name}:exercise.id] exercise.id '{eid}' 重复"
                            )
                        seen_exercise_ids.add(eid)
                except ContentLintError as e:
                    errors.append(str(e))

            # 与 catalog 的一致性校验（catalog.yml 存在时）
            if track_by_key:
                track = frontmatter.get("track") or ""
                if track and track not in track_by_key:
                    errors.append(
                        f"[{file_name}:track] track '{track}' 不在 catalog 中: "
                        f"{sorted(track_by_key)}"
                    )
                elif track and track_by_key[track].get("category"):
                    expected = track_by_key[track]["category"]
                    actual = frontmatter.get("category")
                    if actual != expected:
                        errors.append(
                            f"[{file_name}:category] 与 track '{track}' 的 category "
                            f"'{expected}' 不一致（实际 '{actual}'）"
                        )

            if slug:
                lessons[slug] = {
                    "file": file_name,
                    "prerequisites": frontmatter.get("prerequisites") or [],
                    "recommended_next": frontmatter.get("recommended_next") or [],
                    "examples": frontmatter.get("examples") or [],
                }

        except ContentLintError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"[{file_name}] 读取失败: {e}")

    # 引用图校验：引用必须存在，prerequisites 图必须无环
    errors.extend(_lint_reference_graph(lessons))
    # 示例引用校验：课程 frontmatter 的 examples 必须存在于 content/examples
    example_slugs = {
        raw.get("slug")
        for raw in load_all_examples(content_dir)
        if raw.get("slug")
    }
    for slug, meta in lessons.items():
        for ref in meta["examples"]:
            if ref not in example_slugs:
                errors.append(
                    f"[{meta['file']}:examples] 引用了不存在的示例 '{ref}'"
                )
    return errors


def _load_catalog_safely(content_dir: Path) -> dict[str, Any]:
    """读取 catalog.yml；缺失或非法时返回空 dict（由调用方决定是否报错）。"""
    catalog_file = content_dir / "catalog.yml"
    if not catalog_file.exists():
        return {}
    try:
        catalog = yaml.safe_load(catalog_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(catalog, dict):
        return {}
    try:
        model = ContentCatalog.model_validate(catalog)
    except Exception:
        return {}
    return model.model_dump(mode="json")


def _lint_reference_graph(
    lessons: dict[str, dict[str, Any]],
) -> list[str]:
    """校验 prerequisite/recommended_next 引用存在，且 prerequisites 图无环。"""
    errors: list[str] = []

    for slug, meta in lessons.items():
        file_name = meta["file"]
        for ref in meta["recommended_next"]:
            if ref not in lessons:
                errors.append(
                    f"[{file_name}:recommended_next] 引用了不存在的课程 '{ref}'"
                )
        for ref in meta["prerequisites"]:
            if ref not in lessons:
                errors.append(
                    f"[{file_name}:prerequisites] 引用了不存在的课程 '{ref}'"
                )

    # 沿 prerequisites 的 DFS 环检测
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(slug: str, path: list[str]) -> None:
        if slug in visiting:
            cycle = " -> ".join(path + [slug])
            errors.append(f"[{lessons[slug]['file']}:prerequisites] 检测到课程图环: {cycle}")
            return
        if slug in visited or slug not in lessons:
            return
        visiting.add(slug)
        for ref in lessons[slug]["prerequisites"]:
            visit(ref, path + [slug])
        visiting.discard(slug)
        visited.add(slug)

    for slug in lessons:
        visit(slug, [])

    return errors


def load_catalog(content_dir: Path | None = None) -> dict[str, Any]:
    """
    Load the learning platform catalog.

    The catalog is optional so existing content remains usable while the
    platform moves from a fixed Polars/DuckDB site to configurable topics.
    """
    if content_dir is None:
        content_dir = Path(__file__).parent.parent.parent / "content"

    catalog_file = content_dir / "catalog.yml"
    if not catalog_file.exists():
        return {
            "platform": {
                "name": "Learn DA",
                "title": "交互式学习平台",
                "subtitle": "通过课程、练习和 AI 助手持续学习",
            },
            "topics": [
                {
                    "key": "data-analysis",
                    "label": "数据分析",
                    "description": "Polars、DuckDB 与现代数据分析工作流",
                    "color": "blue",
                }
            ],
            "tracks": [
                {
                    "key": "polars_basics",
                    "topic": "data-analysis",
                    "label": "Polars 基础",
                    "description": "高性能 DataFrame 学习路径",
                    "start_lesson": "polars-basics",
                },
                {
                    "key": "duckdb_basics",
                    "topic": "data-analysis",
                    "label": "DuckDB 基础",
                    "description": "本地 SQL 分析学习路径",
                    "start_lesson": "duckdb-analytics",
                },
            ],
        }

    try:
        catalog = yaml.safe_load(catalog_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        catalog = {}

    return {
        "platform": catalog.get("platform", {}),
        "topics": catalog.get("topics", []),
        "tracks": catalog.get("tracks", []),
    }


def load_example_from_file(file_path: Path) -> dict[str, Any] | None:
    """
    从单个 Markdown 文件加载示例
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(content)

        if not frontmatter:
            return None

        # 提取代码（第一个 python 代码块）
        code_match = re.search(r"```python\s*\n(.*?)\n```", body, re.DOTALL)
        code = code_match.group(1).strip() if code_match else ""

        example = {
            "slug": frontmatter.get("slug"),
            "title": frontmatter.get("title"),
            "topic": frontmatter.get("topic"),
            "summary": frontmatter.get("summary", ""),
            "code": code,
        }

        # 验证必需字段
        if not example["slug"] or not example["title"]:
            print(f"[ContentLoader] Warning: {file_path.name} 缺少 slug 或 title")
            return None

        return example

    except Exception as e:
        print(f"[ContentLoader] Error loading {file_path}: {e}")
        return None


def load_all_lessons(content_dir: Path | None = None) -> list[dict[str, Any]]:
    """
    加载所有课程
    """
    if content_dir is None:
        content_dir = Path(__file__).parent.parent.parent / "content"

    lessons_dir = content_dir / "lessons"
    if not lessons_dir.exists():
        print(f"[ContentLoader] Lessons directory not found: {lessons_dir}")
        return []

    lessons = []
    for md_file in sorted(lessons_dir.glob("*.md")):
        lesson = load_lesson_from_file(md_file)
        if lesson:
            lessons.append(lesson)
            print(f"[ContentLoader] Loaded lesson: {lesson['slug']}")

    # 按 order 排序
    lessons.sort(key=lambda x: x.get("order", 0))

    return lessons


def load_all_examples(content_dir: Path | None = None) -> list[dict[str, Any]]:
    """
    加载所有示例
    """
    if content_dir is None:
        content_dir = Path(__file__).parent.parent.parent / "content"

    examples_dir = content_dir / "examples"
    if not examples_dir.exists():
        print(f"[ContentLoader] Examples directory not found: {examples_dir}")
        return []

    examples = []
    for md_file in sorted(examples_dir.glob("*.md")):
        example = load_example_from_file(md_file)
        if example:
            examples.append(example)
            print(f"[ContentLoader] Loaded example: {example['slug']}")

    return examples
