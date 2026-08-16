"""内容 Catalog 深模块（阶段 4 Task 1）。

- ``build_content_index``：启动时 lint + 加载 + 版本哈希，构建只读索引；
  任何 lint 错误都会抛出，阻止带病内容启动（fail closed）。
- ``get_content_index``：进程级单例，所有消费方共享同一索引，
  运行时不再逐请求扫描文件系统。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .content_loader import (
    lint_content,
    load_all_lessons,
    load_catalog,
)
from .content_schemas import ContentIndex, ContentLintError

_INDEX: ContentIndex | None = None


def _content_version(content_dir: Path) -> str:
    """对全部内容文件内容计算 sha256，作为内容版本标识。"""
    hasher = hashlib.sha256()
    files = sorted(content_dir.rglob("*.md")) + sorted(content_dir.rglob("*.yml"))
    for f in files:
        try:
            hasher.update(f.read_bytes())
        except OSError:
            continue
    return hasher.hexdigest()[:16]


def build_content_index(content_dir: Path | None = None) -> ContentIndex:
    """lint 全部内容并构建不可变索引；有错误则抛出。

    校验失败（含 catalog 与引用图问题）直接抛出，杜绝"启动成功但运行时
    缺课断链"的静默失败。
    """
    if content_dir is None:
        content_dir = Path(__file__).parent.parent.parent / "content"

    issues = lint_content(content_dir)
    if issues:
        raise ContentLintError(
            "内容校验失败：\n" + "\n".join(f"  {e}" for e in issues)
        )

    lessons = load_all_lessons(content_dir)
    catalog = load_catalog(content_dir)

    return ContentIndex(
        lessons=lessons,
        catalog=catalog,
        content_version=_content_version(content_dir),
    )


def get_content_index() -> ContentIndex:
    """获取进程级共享内容索引（懒构建，首次调用后缓存）。"""
    global _INDEX
    if _INDEX is None:
        _INDEX = build_content_index()
    return _INDEX


def reset_content_index() -> None:
    """重置索引缓存（仅测试与热重载使用）。"""
    global _INDEX
    _INDEX = None


def preload_content_index() -> ContentIndex:
    """启动时预热：构建并缓存索引，内容错误直接向外抛出阻断启动。"""
    global _INDEX
    _INDEX = build_content_index()
    return _INDEX
