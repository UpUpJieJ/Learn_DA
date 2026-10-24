"""断言 DSL v2（骨架）：在学员进程内、最后一个重放单元格之后求值。

设计见 ``docs/learning-workspace-redesign-2026-10-21.md`` §6。要点：

* **单进程内联**：断言尾巴追加在重放程序末尾，因此能直接看到学员定义的变量
  （``orders``、``region_stats`` …）。不落盘、不通过网络传变量。
* **参考结果内存注入**：``ref``（parquet / json 字节）以 base64 内联，学员的
  沙箱目录里看不到 ``expected/``。
* **四型断言**：``expr_true`` / ``frame_equal`` / ``schema`` / ``sql_rows``。
* **失败必须给 actual**（``repr`` 截断 500 字符），这是"结构化诊断"的来源。
* **弱保证**：断言与学员代码同进程，理论上可读父进程内存；威胁模型是
  "防误用不防恶意"，靠 ``RunEvent`` / ``TaskAttempt`` 留痕，不做强隔离。

本模块只做「校验 + 生成尾巴 + 解析结果」，求值实现在
:mod:`app.practice.assertion_runtime`（同一份代码既能在服务端直接调用，也能
被沙箱内按路径加载）。两种尾巴：

* ``runtime_path=None``（默认）：把运行时源码内联进程序，自包含、无外部依赖，
  适合测试与本地 lint；代价是程序会多出十几 KB。
* ``runtime_path="…/assertion_runtime.py"``：尾巴用 ``importlib`` 按绝对路径
  加载沙箱里已有的那份实现，**只有几百字节**——M2 接 ``execute_session``
  时应走这条（现有执行接口对 code 有 5000 字符上限，内联运行时会直接超限）。

超时是**事后判定**：v1 用 ``PER_ASSERTION_TIMEOUT_MS`` / ``TOTAL_BUDGET_MS``
把超时的断言标记为 ``timeout`` / ``skipped``，不做线程级抢占（复杂且易崩）。
真正的硬超时由 Runner 的整体执行超时兜底。
"""

from __future__ import annotations

import json
from base64 import b64encode
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.practice import assertion_runtime
from app.practice.assertion_runtime import (
    ACTUAL_LIMIT,
    PER_ASSERTION_TIMEOUT_MS,
    TOTAL_BUDGET_MS,
)

ASSERTION_MARKER = "__LEARN_DA_ASSERTIONS__"
SUPPORTED_TYPES = ("expr_true", "frame_equal", "schema", "sql_rows")

_RUNTIME_PATH = Path(assertion_runtime.__file__).resolve()


class AssertionSpecError(ValueError):
    """断言定义不合法（内容侧错误，应在 lint 阶段拦住）。"""


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def validate_assertions(raw: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """校验并归一化断言定义；不合法直接抛 :class:`AssertionSpecError`。"""
    assertions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, item in enumerate(raw or []):
        if not isinstance(item, Mapping):
            raise AssertionSpecError(f"第 {index + 1} 条断言不是映射")
        spec = dict(item)

        assertion_id = spec.get("id")
        if not isinstance(assertion_id, str) or not assertion_id.strip():
            raise AssertionSpecError(f"第 {index + 1} 条断言缺少字符串 id")
        if assertion_id in seen:
            raise AssertionSpecError(f"断言 id 重复：{assertion_id}")
        seen.add(assertion_id)

        kind = spec.get("type")
        if kind not in SUPPORTED_TYPES:
            raise AssertionSpecError(
                f"断言 {assertion_id} 的类型 {kind!r} 不受支持，"
                f"只能是 {' / '.join(SUPPORTED_TYPES)}"
            )

        normalized: dict[str, Any] = {
            "id": assertion_id,
            "type": kind,
            "title": spec.get("title") or "",
        }

        if kind == "expr_true":
            expr = spec.get("expr")
            if not isinstance(expr, str) or not expr.strip():
                raise AssertionSpecError(f"断言 {assertion_id} 缺少 expr")
            if "__" in expr:
                raise AssertionSpecError(
                    f"断言 {assertion_id} 的表达式不允许访问双下划线名称"
                )
            normalized["expr"] = expr
        elif kind == "frame_equal":
            normalized["var"] = _require_var(assertion_id, spec)
            normalized["ref"] = _require_ref(assertion_id, spec)
            normalized["order_matters"] = bool(spec.get("order_matters", True))
            normalized["rtol"] = float(spec.get("rtol", 1e-6))
            normalized["atol"] = float(spec.get("atol", 0.0))
        elif kind == "schema":
            normalized["var"] = _require_var(assertion_id, spec)
            columns = spec.get("columns")
            dtypes = spec.get("dtypes")
            if not columns and not dtypes:
                raise AssertionSpecError(
                    f"断言 {assertion_id} 至少需要 columns 或 dtypes"
                )
            if columns is not None:
                if not isinstance(columns, list) or not all(
                    isinstance(name, str) for name in columns
                ):
                    raise AssertionSpecError(
                        f"断言 {assertion_id} 的 columns 必须是字符串列表"
                    )
                normalized["columns"] = list(columns)
                # columns 默认是"必须包含"（额外列不判错）；exact=True 才要求完全一致
                normalized["exact"] = bool(spec.get("exact", False))
            if dtypes is not None:
                if not isinstance(dtypes, Mapping):
                    raise AssertionSpecError(
                        f"断言 {assertion_id} 的 dtypes 必须是映射"
                    )
                normalized["dtypes"] = {str(k): str(v) for k, v in dtypes.items()}
        else:  # sql_rows
            query = spec.get("query")
            if not isinstance(query, str) or not query.strip():
                raise AssertionSpecError(f"断言 {assertion_id} 缺少 query")
            normalized["query"] = query
            normalized["ref"] = _require_ref(assertion_id, spec)
            normalized["order_matters"] = bool(spec.get("order_matters", False))
            normalized["rtol"] = float(spec.get("rtol", 1e-6))
            normalized["atol"] = float(spec.get("atol", 0.0))
            # 可选：用哪条 duckdb 连接；缺省时用 duckdb 的默认连接
            normalized["connection"] = str(spec.get("connection") or "con")

        if spec.get("on_fail"):
            normalized["on_fail"] = str(spec.get("on_fail"))
        assertions.append(normalized)

    return assertions


def _require_var(assertion_id: str, spec: Mapping[str, Any]) -> str:
    var = spec.get("var")
    if not isinstance(var, str) or not var.strip():
        raise AssertionSpecError(f"断言 {assertion_id} 缺少 var")
    return var


def _require_ref(assertion_id: str, spec: Mapping[str, Any]) -> str:
    ref = spec.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        raise AssertionSpecError(f"断言 {assertion_id} 缺少 ref")
    return ref


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

_FOOTER_HEADER = """\
# ---- learn_da assertions (v2) ----
import json as _ld_json
_ld_marker = {marker}
_ld_emit = {emit}
_ld_spec = {spec}
_ld_refs = {refs}
"""

_SELF_CONTAINED = """\
_ld_ns = {"__name__": "_learn_da_assertion_runtime"}
exec(compile(_ld_source, "<learn_da_assertion_runtime>", "exec"), _ld_ns)
_ld_results = _ld_ns["run"](globals(), _ld_spec, _ld_refs)
"""

_LOAD_BY_PATH = """\
import importlib.util as _ld_ilu
_ld_file = {runtime_path!r}
_ld_loader = _ld_ilu.spec_from_file_location("_learn_da_assertion_runtime", _ld_file)
_ld_ns = _ld_ilu.module_from_spec(_ld_loader)
_ld_loader.loader.exec_module(_ld_ns)
_ld_results = _ld_ns.run(globals(), _ld_spec, _ld_refs)
"""

_FOOTER_EMIT = """
if _ld_emit:
    print("")
    print(_ld_marker + _ld_json.dumps(_ld_results, ensure_ascii=False))
"""


def render_assertion_source(
    assertions: Iterable[Mapping[str, Any]] | None,
    refs: Mapping[str, bytes] | None = None,
    *,
    emit: bool = True,
    runtime_path: str | Path | None = None,
) -> str:
    """生成追加到重放程序末尾的断言源码。

    Args:
        assertions: 断言定义（会先走 :func:`validate_assertions`）。
        refs: ``ref`` 名称 → 参考结果字节（parquet / json），以 base64 内联。
        emit: 是否打印 :data:`ASSERTION_MARKER` 行供 Runner 解析。
        runtime_path: 给了就按路径加载沙箱内的运行时（尾巴只有几百字节）；
            不给则把运行时源码内联进程序（自包含）。
    """
    normalized = validate_assertions(assertions)
    encoded = {
        name: b64encode(payload).decode("ascii")
        for name, payload in (refs or {}).items()
    }
    missing = sorted(
        {spec["ref"] for spec in normalized if "ref" in spec} - set(encoded)
    )
    if missing:
        raise AssertionSpecError("缺少参考结果：" + ", ".join(missing))

    footer = _FOOTER_HEADER.format(
        marker=repr(ASSERTION_MARKER),
        emit=bool(emit),
        # repr 而不是 json.dumps：这段源码会被 Python 直接解析，
        # JSON 的 true/false/null 不是合法 Python 字面量。
        spec=repr(normalized),
        refs=repr(encoded),
    )
    if runtime_path is None:
        source = _RUNTIME_PATH.read_text(encoding="utf-8")
        footer += "_ld_source = " + repr(source) + "\n" + _SELF_CONTAINED
    else:
        footer += _LOAD_BY_PATH.format(runtime_path=str(runtime_path))
    return footer + _FOOTER_EMIT


# ---------------------------------------------------------------------------
# 求值 / 解析
# ---------------------------------------------------------------------------


def evaluate_assertions(
    assertions: Iterable[Mapping[str, Any]] | None,
    namespace: dict[str, Any],
    refs: Mapping[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    """在给定命名空间里求值断言（服务端 lint / 测试用，不经子进程）。"""
    normalized = validate_assertions(assertions)
    encoded = {
        name: b64encode(payload).decode("ascii")
        for name, payload in (refs or {}).items()
    }
    return assertion_runtime.run(dict(namespace), normalized, encoded)


def parse_assertion_output(stdout: str) -> tuple[list[dict[str, Any]], str]:
    """从执行输出里剥离断言结果。

    Returns:
        ``(results, clean_stdout)``；没有标记行时返回 ``([], stdout)``。
    """
    if ASSERTION_MARKER not in stdout:
        return [], stdout
    kept: list[str] = []
    results: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if line.startswith(ASSERTION_MARKER):
            try:
                results = json.loads(line[len(ASSERTION_MARKER):])
            except json.JSONDecodeError:
                results = []
            continue
        kept.append(line)
    # 尾巴会在标记行前空一行，避免标记粘在学员最后一行输出后面；这里把这行去掉
    clean = "\n".join(kept).rstrip("\n")
    if clean and stdout.endswith("\n"):
        clean += "\n"
    return results, clean


def summarize(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """把断言结果压成一份给人看的摘要（喂 AI 助手 / 前端失败卡片）。"""
    items = list(results)
    failed = [item for item in items if item.get("status") != "passed"]
    return {
        "total": len(items),
        "passed": len(items) - len(failed),
        "allPassed": bool(items) and not failed,
        "firstFailure": failed[0] if failed else None,
    }


__all__ = [
    "ASSERTION_MARKER",
    "ACTUAL_LIMIT",
    "PER_ASSERTION_TIMEOUT_MS",
    "TOTAL_BUDGET_MS",
    "SUPPORTED_TYPES",
    "AssertionSpecError",
    "evaluate_assertions",
    "parse_assertion_output",
    "render_assertion_source",
    "summarize",
    "validate_assertions",
]