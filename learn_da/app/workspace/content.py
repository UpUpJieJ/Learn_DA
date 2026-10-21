"""课程工作区定义（内容格式 v2，改版 M1）。

课程 frontmatter 里的 ``workspace`` 块描述一个可重放的单元格序列与任务：

.. code-block:: yaml

    workspace:
      datasets:
        - ecommerce/orders.csv
      cells:
        - id: c1
          kind: starter
          code: |
            import polars as pl
            orders = pl.read_csv("data/ecommerce/orders.csv")
        - id: c2
          kind: task
          task_id: t1
          code: |
            # TODO: 按 region 聚合
      tasks:
        - id: t1
          title: 按区域统计销售额
          cell: c2
          objective: |
            ...
          assertions:
            - id: a1
              type: expr_true
              title: 结果包含 revenue 列
              expr: "'revenue' in region_stats.columns"

内容侧的校验在这里做（fail-closed）：单元格 id 唯一、任务必须指向存在的
单元格、断言必须通过 DSL 校验、数据集路径必须位于 ``content/datasets`` 下。
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.practice.assertions import validate_assertions

CONTENT_DIR = Path(__file__).resolve().parents[2] / "content"
DATASET_DIR = CONTENT_DIR / "datasets"
RUNTIME_PATH = Path(__file__).resolve().parent.parent / "practice" / "assertion_runtime.py"

MAX_DATASET_BYTES = 5 * 1024 * 1024
MAX_TOTAL_DATASET_BYTES = 8 * 1024 * 1024

MAX_CELLS = 40


class WorkspaceContentError(ValueError):
    """课程工作区定义不合法。"""


@dataclass(frozen=True)
class WorkspaceCell:
    cell_id: str
    kind: str
    language: str
    code: str
    task_id: str | None = None


@dataclass(frozen=True)
class WorkspaceTask:
    task_id: str
    title: str
    cell_id: str
    objective: str = ""
    assertions: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkspaceSpec:
    lesson_slug: str
    datasets: tuple[str, ...]
    cells: tuple[WorkspaceCell, ...]
    tasks: tuple[WorkspaceTask, ...]

    def cell(self, cell_id: str) -> WorkspaceCell:
        for item in self.cells:
            if item.cell_id == cell_id:
                return item
        raise WorkspaceContentError(f"未知单元格：{cell_id}")

    def task(self, task_id: str) -> WorkspaceTask:
        for item in self.tasks:
            if item.task_id == task_id:
                return item
        raise WorkspaceContentError(f"未知任务：{task_id}")

    def assertions_for_cell(self, cell_id: str) -> list[dict[str, Any]]:
        for task in self.tasks:
            if task.cell_id == cell_id:
                return list(task.assertions)
        return []


def _safe_dataset_path(name: str) -> Path:
    cleaned = str(name).replace("\\", "/").strip()
    if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/"):
        raise WorkspaceContentError(f"数据集路径不合法：{name!r}")
    path = (DATASET_DIR / cleaned).resolve()
    try:
        path.relative_to(DATASET_DIR.resolve())
    except ValueError as exc:
        raise WorkspaceContentError(f"数据集路径不合法：{name!r}") from exc
    if not path.is_file():
        raise WorkspaceContentError(f"数据集不存在：{cleaned}")
    if path.stat().st_size > MAX_DATASET_BYTES:
        raise WorkspaceContentError(f"数据集超过 5MB：{cleaned}")
    return path


def load_workspace(lesson: dict[str, Any]) -> WorkspaceSpec | None:
    """从课程 dict 里解析工作区定义；没有 ``workspace`` 块时返回 ``None``。"""
    raw = lesson.get("workspace")
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise WorkspaceContentError("workspace 必须是映射")

    slug = str(lesson.get("slug") or "")
    raw_cells = raw.get("cells")
    if not isinstance(raw_cells, list) or not raw_cells:
        raise WorkspaceContentError("workspace.cells 必须是非空列表")
    if len(raw_cells) > MAX_CELLS:
        raise WorkspaceContentError(f"单元格数量超过 {MAX_CELLS}")

    cells: list[WorkspaceCell] = []
    seen: set[str] = set()
    for entry in raw_cells:
        if not isinstance(entry, dict):
            raise WorkspaceContentError("workspace.cells 的元素必须是映射")
        cell_id = str(entry.get("id") or "").strip()
        if not cell_id:
            raise WorkspaceContentError("单元格缺少 id")
        if cell_id in seen:
            raise WorkspaceContentError(f"单元格 id 重复：{cell_id}")
        seen.add(cell_id)
        kind = str(entry.get("kind") or "task")
        if kind not in {"starter", "task", "scratch"}:
            raise WorkspaceContentError(f"未知单元格类型：{kind}")
        language = str(entry.get("language") or "python")
        code = entry.get("code") or ""
        if not isinstance(code, str):
            raise WorkspaceContentError("单元格 code 必须是字符串")
        if len(code) > 20000:
            raise WorkspaceContentError(f"单元格 {cell_id} 代码超过 20000 字符")
        cells.append(
            WorkspaceCell(
                cell_id=cell_id,
                kind=kind,
                language=language,
                code=code,
                task_id=(str(entry["task_id"]) if entry.get("task_id") else None),
            )
        )

    tasks: list[WorkspaceTask] = []
    seen_tasks: set[str] = set()
    for entry in raw.get("tasks") or []:
        if not isinstance(entry, dict):
            raise WorkspaceContentError("workspace.tasks 的元素必须是映射")
        task_id = str(entry.get("id") or "").strip()
        if not task_id or task_id in seen_tasks:
            raise WorkspaceContentError(f"任务 id 缺失或重复：{task_id!r}")
        seen_tasks.add(task_id)
        cell_id = str(entry.get("cell") or "")
        if cell_id not in seen:
            raise WorkspaceContentError(f"任务 {task_id} 指向不存在的单元格 {cell_id!r}")
        try:
            assertions = validate_assertions(entry.get("assertions"))
        except ValueError as exc:
            raise WorkspaceContentError(f"任务 {task_id} 的断言不合法：{exc}") from exc
        if not assertions:
            raise WorkspaceContentError(f"任务 {task_id} 至少需要一条断言")
        tasks.append(
            WorkspaceTask(
                task_id=task_id,
                title=str(entry.get("title") or task_id),
                cell_id=cell_id,
                objective=str(entry.get("objective") or ""),
                assertions=tuple(assertions),
            )
        )

    datasets: list[str] = []
    total = 0
    for name in raw.get("datasets") or []:
        path = _safe_dataset_path(str(name))
        total += path.stat().st_size
        if total > MAX_TOTAL_DATASET_BYTES:
            raise WorkspaceContentError("数据集总量超过 8MB")
        datasets.append(str(name).replace("\\", "/"))

    return WorkspaceSpec(
        lesson_slug=slug,
        datasets=tuple(datasets),
        cells=tuple(cells),
        tasks=tuple(tasks),
    )


_dataset_cache: dict[str, str] = {}
_runtime_cache: str | None = None


def dataset_payload(names: list[str] | tuple[str, ...]) -> dict[str, str]:
    """把数据集编码成 base64（按请求发给 Runner，落进沙箱工作区）。"""
    payload: dict[str, str] = {}
    for name in names:
        if name not in _dataset_cache:
            path = _safe_dataset_path(name)
            _dataset_cache[name] = base64.b64encode(path.read_bytes()).decode("ascii")
        payload[name] = _dataset_cache[name]
    return payload


def runtime_source() -> str:
    """断言运行时的源码——由后端随请求下发，沙箱镜像无需重建。"""
    global _runtime_cache
    if _runtime_cache is None:
        _runtime_cache = RUNTIME_PATH.read_text(encoding="utf-8")
    return _runtime_cache