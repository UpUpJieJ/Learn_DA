"""工作区课程内容自检：起步代码必须判失败，参考解必须整链通过。

不依赖 Runner：断言在进程内用 `app/practice/assertion_runtime.py` 求值，
单元格按「重放语义」在同一命名空间里顺序 exec，`data/` 由 `content/datasets` 拷进临时工作目录，
所以课程代码里写的 `data/ecommerce/orders.csv` 这类相对路径能直接跑。

对应设计稿 §7 的 lint 规则 L2/L3/L4/L6：
- L2 断言引用的变量在参考解执行后存在（参考解全通过即覆盖）
- L3 starter 在该任务断言下必须 fail
- L4 参考解在完整重放下全部 pass
- L6 数据集存在且总量 ≤ Runner 的请求上限（默认 2MB）
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from app.practice.assertions import evaluate_assertions
from app.workspace.content import (
    DATASET_DIR,
    EXPECTED_DIR,
    MAX_DATASET_BYTES,
    WorkspaceSpec,
    load_workspace,
)
from scripts.workspace_solutions import SOLUTIONS

LESSON_DIR = Path(__file__).resolve().parent.parent / "content" / "lessons"


def _lesson_files() -> list[Path]:
    return sorted(LESSON_DIR.glob("*.md"))


def _workspace_specs() -> dict[str, tuple[dict[str, Any], WorkspaceSpec]]:
    from app.core.content_loader import load_lesson_from_file

    specs: dict[str, tuple[dict[str, Any], WorkspaceSpec]] = {}
    for path in _lesson_files():
        lesson = load_lesson_from_file(path)
        if not lesson or not lesson.get("workspace"):
            continue
        spec = load_workspace(lesson)
        assert spec is not None, f"{path.name}: workspace 存在但解析失败"
        specs[lesson["slug"]] = (lesson, spec)
    return specs


SPECS = _workspace_specs()


@pytest.fixture()
def sandbox_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 content/datasets 拷成 tmp/data，并 chdir 过去（模拟沙箱挂载点）。"""
    data = tmp_path / "data"
    shutil.copytree(DATASET_DIR, data)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _replay(
    spec: WorkspaceSpec,
    codes: dict[str, str],
    *,
    stop_at: str | None = None,
) -> dict[str, Any]:
    """按顺序 exec 单元格；`codes` 覆盖指定格的代码（缺省用内容里的代码）。"""
    namespace: dict[str, Any] = {"__name__": "__workspace__"}
    for cell in spec.cells:
        code = codes.get(cell.cell_id, cell.code)
        exec(compile(code, f"<cell:{cell.cell_id}>", "exec"), namespace)  # noqa: S102 —— 课程内容自检
        if stop_at and cell.cell_id == stop_at:
            break
    return namespace


def _statuses(results: list[dict[str, Any]]) -> dict[str, str]:
    return {str(item["id"]): str(item["status"]) for item in results}


def _refs(spec: WorkspaceSpec) -> dict[str, bytes]:
    """参考结果的原始字节（frame_equal / sql_rows 需要）。

    ``evaluate_assertions`` 自己负责 base64，所以这里给未编码的 bytes；
    线上走 ``refs_payload`` 得到已编码的 str 发给 Runner。
    """
    return {name: (EXPECTED_DIR / name).read_bytes() for name in spec.ref_names()}


@pytest.mark.parametrize("slug", sorted(SPECS) or ["_none_"])
def test_workspace_lesson_contract(slug: str, sandbox_root: Path) -> None:
    if slug == "_none_":  # 还没有任何工作区课程时不让用例失败
        pytest.skip("没有课程声明 workspace")
    _lesson, spec = SPECS[slug]

    assert len(spec.tasks) >= 2, f"{slug}: 任务太少（{len(spec.tasks)} 个），至少 2 个"
    assert spec.cells, f"{slug}: 没有单元格"

    solutions = SOLUTIONS.get(slug)
    assert solutions is not None, f"{slug}: 缺少参考解，请补 scripts/workspace_solutions.py"
    missing = {cell.cell_id for cell in spec.cells if cell.kind == "task"} - set(solutions)
    assert not missing, f"{slug}: 参考解缺少 task 格 {sorted(missing)}"

    # L3：起步代码在该任务断言下必须判失败
    for task in spec.tasks:
        namespace = _replay(spec, solutions, stop_at=task.cell_id)
        results = evaluate_assertions(
            spec.assertions_for_cell(task.cell_id), namespace, _refs(spec)
        )
        starter_namespace = _replay(spec, {}, stop_at=task.cell_id)
        starter_results = evaluate_assertions(
            spec.assertions_for_cell(task.cell_id), starter_namespace, _refs(spec)
        )
        assert any(item["status"] != "passed" for item in starter_results), (
            f"{slug}/{task.id}: 起步代码直接通过，等于白给。"
            f"断言结果={_statuses(starter_results)}"
        )
        # 参考解跑到该任务为止，该任务的断言必须全过
        assert all(item["status"] == "passed" for item in results), (
            f"{slug}/{task.id}: 参考解未全通过 {_statuses(results)}"
        )

    # L4：参考解在完整序列下全部 pass
    namespace = _replay(spec, solutions)
    for task in spec.tasks:
        results = evaluate_assertions(
            spec.assertions_for_cell(task.cell_id), namespace, _refs(spec)
        )
        assert all(item["status"] == "passed" for item in results), (
            f"{slug}/{task.id}: 整链重放后未全通过 {_statuses(results)}"
        )


@pytest.mark.parametrize("slug", sorted(SPECS) or ["_none_"])
def test_workspace_datasets_are_small(slug: str, sandbox_root: Path) -> None:
    if slug == "_none_":
        pytest.skip("没有课程声明 workspace")
    _lesson, spec = SPECS[slug]
    total = 0
    for name in spec.datasets:
        path = DATASET_DIR / name
        assert path.is_file(), f"{slug}: 数据集不存在 {name}"
        total += path.stat().st_size
    assert total <= MAX_DATASET_BYTES, (
        f"{slug}: 数据集总量 {total} 超过 {MAX_DATASET_BYTES} 字节"
    )
