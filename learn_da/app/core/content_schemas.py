"""内容 Catalog 的 Pydantic schema 与不可变内容索引（阶段 4 Task 1）。

- ``LessonFrontmatter`` / ``ContentCatalog``：内容发布前的 schema 校验；
- ``ContentIndex``：启动时构建一次、全进程只读共享的内容索引。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class ContentLintError(Exception):
    """内容校验错误（含文件名，fail closed）"""

    def __init__(self, message: str, file_name: str = ""):
        self.file_name = file_name
        super().__init__(f"[{file_name}] {message}" if file_name else message)


class ExerciseFrontmatter(BaseModel):
    """frontmatter 中的练习定义（确定性判定）"""

    id: str
    title: str = ""
    language: str = "python"
    starter_code: str = ""
    objective: str = ""
    hints: list[str] = Field(default_factory=list)
    validator: dict[str, Any]


class LessonFrontmatter(BaseModel):
    """课程 frontmatter 的发布 schema（字段级校验）"""

    id: int
    slug: str
    title: str
    category: str
    difficulty: str
    topic: str = "data-analysis"
    description: str = ""
    estimated_minutes: int = 15
    order: int = 0
    tags: list[str] = Field(default_factory=list)
    track: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    recommended_next: list[str] = Field(default_factory=list)
    skill_tags: list[str] = Field(default_factory=list)
    prev_lesson: dict[str, Any] | None = None
    next_lesson: dict[str, Any] | None = None
    is_review_friendly: bool = False
    is_branch_point: bool = False
    practice_objective: str = ""
    completion_criteria: list[str] = Field(default_factory=list)
    exercise: ExerciseFrontmatter | None = None


class CatalogTopic(BaseModel):
    key: str
    label: str
    description: str = ""
    color: str = ""


class CatalogTrack(BaseModel):
    key: str
    topic: str
    label: str
    description: str = ""
    start_lesson: str = ""
    category: str = ""
    color: str = ""


class ContentCatalog(BaseModel):
    platform: dict[str, Any] = Field(default_factory=dict)
    topics: list[CatalogTopic] = Field(default_factory=list)
    tracks: list[CatalogTrack] = Field(default_factory=list)


def validate_lesson_frontmatter(
    frontmatter: dict[str, Any], file_name: str
) -> LessonFrontmatter:
    """用 Pydantic 校验 frontmatter；错误转成带文件名的 ContentLintError。"""
    from pydantic import ValidationError

    try:
        return LessonFrontmatter.model_validate(frontmatter)
    except ValidationError as exc:
        first = exc.errors()[0]
        field_path = ".".join(str(p) for p in first.get("loc", ()))
        message = f"{first.get('msg', 'invalid')} (field: {field_path or 'root'})"
        raise ContentLintError(message, file_name) from exc


@dataclass(frozen=True)
class ContentIndex:
    """启动时构建的不可变内容索引。

    lessons 为加载器产出的原始 dict 列表（保持既有消费方契约）；
    catalog 为目录配置；content_version 为全部内容文件的 sha256。
    """

    lessons: list[dict[str, Any]]
    catalog: dict[str, Any]
    content_version: str
    issues: tuple[str, ...] = ()
