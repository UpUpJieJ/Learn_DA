"""从参考解生成断言所需的「预期结果」（``content/expected/``）。

为什么需要它
------------
``frame_equal`` / ``sql_rows`` 两种断言要拿学员的结果跟一份**预期结果**逐行比对，
预期结果以 base64 随请求下发、只在内存里注入（学员的沙箱目录看不到 ``expected/``）。
这份预期结果不能手写——手抄数字就是过去 20 条 ``expr_true`` 魔数断言的来源，
数据一换 seed 就得全量重抄。所以它由本脚本从 ``scripts/solutions`` 的参考解**跑出来**。

用法::

    python scripts/build_expected.py            # 重新生成全部预期结果
    python scripts/build_expected.py --check    # 只校验，和磁盘上的不一致就非零退出

约定
----
* 断言里写 ``ref: 07-t2-channels.parquet``，路径相对于 ``content/expected/``（**不要**带 ``expected/`` 前缀，否则会解析成 ``content/expected/expected/...``）。
* ``frame_equal``：把 ``var`` 指向的变量按 parquet 落盘（保留列名与类型）。
* ``sql_rows``：执行 ``query`` 并把结果行写成 ``{"columns": [...], "rows": [...]}`` 的
  JSON（列名来自 DuckDB 的 description，保证列序稳定）。
* 只有**参考解能跑通**的课才会生成；起步代码跑不通是正常的（那正是它的用途）。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

# 固定单线程再 import polars：分组聚合的浮点求和顺序随线程数变化，
# 多线程下同一份数据两次跑出来的 sum 末位不同，预期结果就不可复现了。
# 学员侧仍是多线程，所以断言用 rtol 容差比对，而不是要求逐位相等。
os.environ.setdefault("POLARS_MAX_THREADS", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.content_loader import load_lesson_from_file  # noqa: E402
from app.workspace.content import (  # noqa: E402
    DATASET_DIR,
    _resolve_expected_path,
    WorkspaceSpec,
    load_workspace,
)

LESSON_DIR = ROOT / "content" / "lessons"


def _specs() -> dict[str, WorkspaceSpec]:
    specs: dict[str, WorkspaceSpec] = {}
    for path in sorted(LESSON_DIR.glob("*.md")):
        lesson = load_lesson_from_file(path)
        if not lesson or not lesson.get("workspace"):
            continue
        # require_refs=False：首轮生成时预期结果文件还不存在
        spec = load_workspace(lesson, require_refs=False)
        if spec is not None:
            specs[str(lesson["slug"])] = spec
    return specs


def _replay(spec: WorkspaceSpec, codes: dict[str, str], stop_at: str) -> dict[str, Any]:
    """按顺序 exec 到 ``stop_at`` 为止，返回共享命名空间（与运行时语义一致）。

    单元格里的 ``print`` 必须吞掉：参考解通常会打印结果表，不吞的话
    ``--check`` 的输出会被这些表格淹没，真正的 drift 反而看不见。
    """
    namespace: dict[str, Any] = {"__name__": "__workspace__"}
    with contextlib.redirect_stdout(io.StringIO()):
        for cell in spec.cells:
            code = codes.get(cell.cell_id, cell.code)
            exec(compile(code, f"<cell:{cell.cell_id}>", "exec"), namespace)  # noqa: S102
            if cell.cell_id == stop_at:
                break
    return namespace


def _dump_frame_equal(value: Any) -> bytes:
    import polars as pl

    frame = value if isinstance(value, pl.DataFrame) else pl.DataFrame(value)
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def _dump_sql_rows(con: Any, query: str) -> bytes:
    cursor = con.execute(query)
    columns = [str(item[0]) for item in cursor.description or []]
    rows = [[_plain(cell) for cell in row] for row in cursor.fetchall()]
    return json.dumps(
        {"columns": columns, "rows": rows}, ensure_ascii=False, sort_keys=False
    ).encode("utf-8")


def _plain(value: Any) -> Any:
    """把 DuckDB 的 Decimal / datetime 之类转成 JSON 能表达的值。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _build(spec: WorkspaceSpec, solutions: dict[str, str]) -> dict[str, bytes]:
    """生成该课所有 ``ref`` 对应的字节。"""
    produced: dict[str, bytes] = {}
    for task in spec.tasks:
        for assertion in task.assertions:
            ref = assertion.get("ref")
            if not isinstance(ref, str) or ref in produced:
                continue
            namespace = _replay(spec, solutions, stop_at=task.cell_id)
            if assertion["type"] == "frame_equal":
                var = assertion["var"]
                if var not in namespace:
                    raise RuntimeError(
                        f"{spec.lesson_slug}/{assertion['id']}: 参考解里没有变量 {var!r}"
                    )
                produced[ref] = _dump_frame_equal(namespace[var])
            elif assertion["type"] == "sql_rows":
                connection = namespace.get(assertion.get("connection") or "con")
                if connection is None:
                    import duckdb

                    connection = duckdb
                produced[ref] = _dump_sql_rows(connection, assertion["query"])
    return produced


def _solution_files() -> dict[str, dict[str, str]]:
    from scripts.workspace_solutions import SOLUTIONS

    return SOLUTIONS


def generate(check: bool) -> int:
    specs = _specs()
    solutions = _solution_files()
    targets = {slug: spec for slug, spec in specs.items() if spec.ref_names()}
    if not targets:
        print("没有课程使用 frame_equal / sql_rows 断言，无需生成预期结果。")
        return 0

    drift: list[str] = []
    written: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copytree(DATASET_DIR, work / "data")
        previous = Path.cwd()
        os.chdir(work)
        try:
            for slug, spec in sorted(targets.items()):
                codes = solutions.get(slug)
                if not codes:
                    drift.append(f"{slug}: 缺少参考解，无法生成预期结果")
                    continue
                try:
                    produced = _build(spec, codes)
                except Exception as exc:  # 参考解跑不通要显式报出来
                    drift.append(f"{slug}: 生成失败 {type(exc).__name__}: {exc}")
                    continue
                for ref, payload in produced.items():
                    path = _resolve_expected_path(ref)
                    if check:
                        if not path.is_file():
                            drift.append(f"{slug}: 缺少预期结果 {ref}")
                        elif path.read_bytes() != payload:
                            drift.append(f"{slug}: 预期结果与参考解不一致 {ref}")
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(payload)
                        written.append(ref)
        finally:
            os.chdir(previous)

    if check:
        for item in drift:
            print(item)
        if drift:
            print(f"\n预期结果校验失败：{len(drift)} 个问题")
            return 1
        print(f"预期结果校验通过：{len(targets)} 门课。")
        return 0

    for item in drift:
        print(item)
    print(f"预期结果已生成：{len(written)} 个文件（{len(targets)} 门课）。")
    return 1 if drift else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="从参考解生成断言预期结果")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只校验磁盘上的预期结果是否与参考解一致（不写文件）",
    )
    args = parser.parse_args()
    return generate(check=args.check)


if __name__ == "__main__":
    sys.exit(main())
