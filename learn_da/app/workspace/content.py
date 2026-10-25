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
EXPECTED_DIR = CONTENT_DIR / "expected"
RUNTIME_PATH = Path(__file__).resolve().parent.parent / "practice" / "assertion_runtime.py"

# 数据集预算必须 ≤ Runner 的 RUNNER_SESSION_MAX_DATASET_BYTES（默认 2_000_000），
# 否则课程能过 content_lint，却在运行时报一个看不懂的 invalid_session_request。
# tests/test_dependency_pins.py 会把这两个数字锁在一起，改一处必须改另一处。
MAX_DATASET_BYTES = 2_000_000
MAX_TOTAL_DATASET_BYTES = 2_000_000

# 参考结果（frame_equal / sql_rows 的 ``ref``）同样随请求下发，跟数据集共用一个
# 字节预算；单个文件额外限制，防止误把大表 dump 进内容目录。
MAX_EXPECTED_BYTES = 200_000
MAX_TOTAL_EXPECTED_BYTES = 2_000_000
# parquet 由 polars 读（保留列名与类型）；json 里可以写 {"columns": [...], "rows": [...]}
EXPECTED_SUFFIXES = (".parquet", ".json")

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
    refs: tuple[str, ...] = ()

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

    def ref_names(self) -> tuple[str, ...]:
        """这门课所有断言引用到的 ``ref`` 名称（去重、保持出现顺序）。"""
        names: list[str] = []
        for task in self.tasks:
            for assertion in task.assertions:
                ref = assertion.get("ref")
                if isinstance(ref, str) and ref not in names:
                    names.append(ref)
        return tuple(names)


def _safe_relative_path(name: str, base_dir: Path, *, what: str) -> Path:
    """把 ``name`` 解析到 ``base_dir`` 下并做存在性校验。"""
    cleaned = str(name).replace("\\", "/").strip()
    if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/"):
        raise WorkspaceContentError(f"{what}路径不合法：{name!r}")
    path = (base_dir / cleaned).resolve()
    try:
        path.relative_to(base_dir.resolve())
    except ValueError as exc:
        raise WorkspaceContentError(f"{what}路径不合法：{name!r}") from exc
    if not path.is_file():
        raise WorkspaceContentError(f"{what}不存在：{cleaned}")
    return path


def _safe_dataset_path(name: str) -> Path:
    path = _safe_relative_path(name, DATASET_DIR, what="数据集")
    if path.stat().st_size > MAX_DATASET_BYTES:
        raise WorkspaceContentError(f"数据集超过 {MAX_DATASET_BYTES // 1000}KB：{name}")
    return path


def _resolve_expected_path(name: str) -> Path:
    """只做路径安全与扩展名校验，不要求文件已存在。

    ``scripts/build_expected.py`` 要用它算出「该写到哪」，此时文件还没生成；
    正常加载课程走 :func:`_safe_expected_path`，仍然 fail-closed。
    """
    cleaned = str(name).replace("\\", "/").strip()
    if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/"):
        raise WorkspaceContentError(f"参考结果路径不合法：{name!r}")
    path = (EXPECTED_DIR / cleaned).resolve()
    try:
        path.relative_to(EXPECTED_DIR.resolve())
    except ValueError as exc:
        raise WorkspaceContentError(f"参考结果路径不合法：{name!r}") from exc
    if path.suffix.lower() not in EXPECTED_SUFFIXES:
        raise WorkspaceContentError(
            f"参考结果必须是 {' / '.join(EXPECTED_SUFFIXES)}：{name}"
        )
    return path


def _safe_expected_path(name: str) -> Path:
    """参考结果路径：必须落在 ``content/expected`` 下、扩展名受限、文件已存在。"""
    path = _resolve_expected_path(name)
    if not path.is_file():
        raise WorkspaceContentError(f"参考结果不存在：{name}")
    if path.stat().st_size > MAX_EXPECTED_BYTES:
        raise WorkspaceContentError(
            f"参考结果超过 {MAX_EXPECTED_BYTES // 1000}KB：{name}"
        )
    return path


def load_workspace(
    lesson: dict[str, Any], *, require_refs: bool = True
) -> WorkspaceSpec | None:
    """从课程 dict 里解析工作区定义；没有 ``workspace`` 块时返回 ``None``。

    ``require_refs=False`` 只校验 ref 的路径与扩展名、不要求文件已生成，
    供 ``scripts/build_expected.py`` 首轮生成使用；线上加载必须走默认值。
    """
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
            raise WorkspaceContentError(
                f"数据集总量超过 {MAX_TOTAL_DATASET_BYTES // 1000}KB"
            )
        datasets.append(str(name).replace("\\", "/"))

    # 断言里写了 ref 的，必须在 content/expected 下真的存在（fail-closed）：
    # 否则要等学员提交到那一步才会以 "error" 形式炸出来，内容问题被藏到最后。
    # 例外：生成预期结果时文件还不存在，走 require_refs=False 只校验路径与扩展名。
    refs: list[str] = []
    expected_total = 0
    for task in tasks:
        for assertion in task.assertions:
            ref = assertion.get("ref")
            if not isinstance(ref, str) or ref in refs:
                continue
            if require_refs:
                path = _safe_expected_path(ref)
                expected_total += path.stat().st_size
                if expected_total > MAX_TOTAL_EXPECTED_BYTES:
                    raise WorkspaceContentError(
                        f"参考结果总量超过 {MAX_TOTAL_EXPECTED_BYTES // 1000}KB"
                    )
            else:
                _resolve_expected_path(ref)
            refs.append(ref)

    return WorkspaceSpec(
        lesson_slug=slug,
        datasets=tuple(datasets),
        cells=tuple(cells),
        tasks=tuple(tasks),
        refs=tuple(refs),
    )


_dataset_cache: dict[str, tuple[int, int, str]] = {}
_expected_cache: dict[str, tuple[int, int, str]] = {}
_runtime_cache: str | None = None


def _cached_payload(
    cache: dict[str, tuple[int, int, str]], name: str, path: Path
) -> str:
    """按 (mtime, size) 缓存 base64，文件被重新生成后自动失效。

    只缓存编码结果不缓存「这个文件存在」这件事——``build_expected.py`` 重新生成
    预期结果后，正在运行的进程必须立刻用上新字节，否则课程改了却仍按旧参考结果判定。
    """
    stat = path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    hit = cache.get(name)
    if hit is not None and (hit[0], hit[1]) == key:
        return hit[2]
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    cache[name] = (key[0], key[1], encoded)
    return encoded


def dataset_payload(names: list[str] | tuple[str, ...]) -> dict[str, str]:
    """把数据集编码成 base64（按请求发给 Runner，落进沙箱工作区）。"""
    payload: dict[str, str] = {}
    for name in names:
        payload[name] = _cached_payload(_dataset_cache, name, _safe_dataset_path(name))
    return payload


def refs_payload(names: list[str] | tuple[str, ...]) -> dict[str, str]:
    """把参考结果编码成 base64（内存注入断言运行时，学员看不到 ``expected/``）。"""
    payload: dict[str, str] = {}
    for name in names:
        payload[name] = _cached_payload(_expected_cache, name, _safe_expected_path(name))
    return payload


def runtime_source() -> str:
    """断言运行时的源码——由后端随请求下发，沙箱镜像无需重建。"""
    global _runtime_cache
    if _runtime_cache is None:
        _runtime_cache = RUNTIME_PATH.read_text(encoding="utf-8")
    return _runtime_cache