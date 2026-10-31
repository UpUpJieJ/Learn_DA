"""Part2 冒烟：用带 polars 的解释器跑真实两进程链路（临时脚本，用完即删）。

runner venv 无 polars，pytest 覆盖不了 polars 表变量往返。本脚本验证旧内部
父进程判定模式；正式后端链路用 scripts/verify_observation_runner.py。本脚本用 learn_da venv 驱动 LocalSubprocessProvider
（driver 与 child 都以同一解释器启动），验证：
1. frame_equal + parquet ref + 正确 polars DataFrame → passed；
2. 数值错误（31 vs 30）→ assertion_failed（判定在 parent，真 refs 比对）；
3. schema 断言的列校验仍然工作。
"""

from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

RUNNER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNNER_ROOT))

import polars as pl  # noqa: E402

from runner.local_provider import LocalSubprocessProvider  # noqa: E402
from runner.schemas import RunnerSessionRequest, SessionCell  # noqa: E402

RUNTIME = (
    RUNNER_ROOT.parent / "learn_da" / "app" / "practice" / "assertion_runtime.py"
).read_text(encoding="utf-8")

expected = pl.DataFrame({"region": ["华东", "华北"], "revenue": [30.0, 40.0]})
buf = io.BytesIO()
expected.write_parquet(buf)
REF_B64 = base64.b64encode(buf.getvalue()).decode("ascii")

GOOD_CODE = (
    "import polars as pl\n"
    "region_stats = pl.DataFrame({'region': ['华东', '华北'], 'revenue': [30.0, 40.0]})\n"
)
BAD_CODE = (
    "import polars as pl\n"
    "region_stats = pl.DataFrame({'region': ['华东', '华北'], 'revenue': [31.0, 40.0]})\n"
)

FRAME_SPEC = {
    "id": "a1",
    "type": "frame_equal",
    "title": "区域收入与参考一致",
    "var": "region_stats",
    "ref": "expected/region_stats.parquet",
    "rtol": 1e-6,
    "atol": 0.0,
}
SCHEMA_SPEC = {
    "id": "a2",
    "type": "schema",
    "title": "列结构",
    "var": "region_stats",
    "columns": ["region", "revenue"],
}


def _request(code: str, assertions: list[dict]) -> RunnerSessionRequest:
    return RunnerSessionRequest(
        requestId="33333333-3333-3333-3333-333333333333",
        cells=[SessionCell(cellId="c1", code=code)],
        datasets={},
        runtime=RUNTIME,
        refs={"expected/region_stats.parquet": REF_B64},
        assertions=assertions,
    )


def main() -> int:
    provider = LocalSubprocessProvider(
        python_executable=sys.executable, timeout_seconds=30
    )

    result = provider.execute_session(_request(GOOD_CODE, [FRAME_SPEC, SCHEMA_SPEC]))
    print("case1 正确数据:", json.dumps(result, ensure_ascii=False)[:400])
    assert result["verdict"] == "passed", f"正确数据应 passed，得到 {result['verdict']}"

    result = provider.execute_session(_request(BAD_CODE, [FRAME_SPEC]))
    print("case2 错误数据:", json.dumps(result, ensure_ascii=False)[:400])
    assert result["verdict"] == "assertion_failed", (
        f"错误数据应 assertion_failed，得到 {result['verdict']}"
    )
    assert result["assertions"][0]["status"] == "failed"

    result = provider.execute_session(
        _request(
            "import polars as pl\n"
            "region_stats = pl.DataFrame({'area': ['华东'], 'revenue': [30.0]})\n",
            [SCHEMA_SPEC],
        )
    )
    print("case3 缺列:", json.dumps(result, ensure_ascii=False)[:400])
    assert result["verdict"] == "assertion_failed"

    print("SMOKE OK: polars JSON 表往返 + 判定隔离在真实链路上成立")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
