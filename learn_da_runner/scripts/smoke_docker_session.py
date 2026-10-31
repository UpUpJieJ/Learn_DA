"""Part2 冒烟（Docker 路径）：验证判定隔离在 Docker 沙箱里的完整链路。

本机没有 Docker，pytest 只覆盖 LocalSubprocessProvider；生产唯一选择是
DockerExecutionProvider，其 stdin 接线（attach_socket + 长度帧，不依赖
EOF）与 nonce 解析只有这条脚本能验证。在有 Docker 的主机上跑：

    python scripts/smoke_docker_session.py

前置条件：本地已构建 ``polars-duckdb-sandbox:pl1.39.3-duck1.5.1-arrow25.0.1`` 镜像（Dockerfile.sandbox）。
参考运行时源码默认取同目录的 ``assertion_runtime.py``，也可用环境变量
``LEARN_DA_RUNTIME`` 指定 learn_da 仓库里的原件。

验证三件事：
1. frame_equal + JSON ref + 正确 polars DataFrame → passed（含 JSON 表
   变量往返：child 序列化 → parent 反序列化 → 判定）；
2. 数值错误（31 vs 30）→ assertion_failed（判定在 parent，真 refs 比对）；
3. expr_true 在容器内仍可用（过渡期语义，判定采信 child 回传）。
"""

from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from pathlib import Path

RUNNER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNNER_ROOT))

from runner.provider import DockerExecutionProvider  # noqa: E402
from runner.schemas import ExecutionStatus, RunnerSessionRequest, SessionCell  # noqa: E402


def _runtime_source() -> str:
    env = os.environ.get("LEARN_DA_RUNTIME")
    candidates = [
        Path(env) if env else None,
        Path(__file__).with_name("assertion_runtime.py"),
        RUNNER_ROOT.parent / "learn_da" / "app" / "practice" / "assertion_runtime.py",
    ]
    for path in candidates:
        if path and path.exists():
            return path.read_text(encoding="utf-8")
    raise SystemExit("找不到 assertion_runtime.py（可用 LEARN_DA_RUNTIME 指定）")


RUNTIME = _runtime_source()

# JSON ref：调用侧无需 polars 即可构造；容器内的 JSON 表往返照样被覆盖
REF_JSON = {"columns": ["region", "revenue"], "rows": [["华东", 30.0], ["华北", 40.0]]}
REF_B64 = base64.b64encode(json.dumps(REF_JSON, ensure_ascii=False).encode("utf-8")).decode("ascii")

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
    "ref": "expected/region_stats.json",
    "rtol": 1e-6,
    "atol": 0.0,
}
EXPR_SPEC = {
    "id": "a2",
    "type": "expr_true",
    "title": "两行结果",
    "expr": "region_stats.height == 2",
}


def _request(code: str, assertions: list[dict]) -> RunnerSessionRequest:
    return RunnerSessionRequest(
        request_id=uuid.uuid4(),
        cells=[SessionCell(cell_id="c1", code=code, language="python")],
        stop_at=None,
        datasets={},
        runtime=RUNTIME,
        refs={"expected/region_stats.json": REF_B64},
        assertions=assertions,
    )


def _run(provider: DockerExecutionProvider, code: str, assertions: list[dict]) -> dict:
    result = provider.execute_session(_request(code, assertions))
    return result


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    provider = DockerExecutionProvider()
    if not provider.ping():
        print("!! Docker 不可用（ping 失败）")
        return 2
    print(f"image = {provider._image}")
    ok = True

    print("[case1] 正确 DataFrame + frame_equal(JSON ref) → 期望 passed")
    r1 = _run(provider, GOOD_CODE, [FRAME_SPEC])
    print(f"  status={r1.get('status')} verdict={r1.get('verdict')} "
          f"assertions={[a.get('status') for a in r1.get('assertions', [])]}")
    ok = ok and r1.get("verdict") == "passed" and r1.get("status") == ExecutionStatus.SUCCESS

    print("[case2] 数值错误 31 vs 30 → 期望 assertion_failed")
    r2 = _run(provider, BAD_CODE, [FRAME_SPEC])
    detail = (r2.get("assertions") or [{}])[0].get("detail") or ""
    actual = (r2.get("assertions") or [{}])[0].get("actual")
    print(f"  status={r2.get('status')} verdict={r2.get('verdict')} detail={detail[:60]!r} actual={str(actual)[:80]!r}")
    ok = ok and r2.get("verdict") == "assertion_failed" and r2.get("status") == ExecutionStatus.SUCCESS

    print("[case3] expr_true 容器内求值 → 期望 passed（过渡期语义）")
    r3 = _run(provider, GOOD_CODE, [EXPR_SPEC])
    print(f"  status={r3.get('status')} verdict={r3.get('verdict')} "
          f"assertions={[a.get('status') for a in r3.get('assertions', [])]}")
    ok = ok and r3.get("verdict") == "passed" and r3.get("status") == ExecutionStatus.SUCCESS

    for label, result in (("case1", r1), ("case2", r2), ("case3", r3)):
        if result.get("status") != ExecutionStatus.SUCCESS:
            print(f"  {label}: errorType={result.get('errorType')} stderr={result.get('stderr')}")

    print()
    print("=" * 60)
    print(f"Docker 判定隔离冒烟：{'3/3 通过' if ok else '!! 有失败'}")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
