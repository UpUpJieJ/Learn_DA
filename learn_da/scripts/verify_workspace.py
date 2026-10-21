"""工作区端到端自检（改版 M1）。

真实链路：创建会话 → 写入参考解 → 逐格执行 → 提交任务。
要求后端与 Runner 都在运行，课程内容里已有 ``workspace`` 块。

用法::

    python scripts/verify_workspace.py --base-url http://127.0.0.1:8000

退出码 0 表示全部通过。
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import Any

import httpx

LESSON = "polars-groupby"

# 参考解：按任务顺序覆盖单元格代码（键是 cell id）
SOLUTIONS: dict[str, str] = {
    "c2": (
        "region_stats = (\n"
        "    orders.group_by('region')\n"
        "    .agg(\n"
        "        pl.col('amount').sum().alias('revenue'),\n"
        "        pl.len().alias('orders'),\n"
        "    )\n"
        "    .sort('revenue', descending=True)\n"
        ")\n"
        "print(region_stats)\n"
    ),
    "c3": (
        "region_share = region_stats.with_columns(\n"
        "    (pl.col('revenue') / pl.col('revenue').sum()).round(2).alias('share')\n"
        ")\n"
        "print(region_share)\n"
    ),
}

TASK_ORDER = ["t1", "t2"]


def _rid() -> str:
    return uuid.uuid4().hex


def _data(response: httpx.Response) -> dict[str, Any]:
    payload = response.json()
    if payload.get("code") != 200:
        raise SystemExit(f"请求失败：{payload}")
    return payload["data"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/") + "/api/v1"

    with httpx.Client(timeout=120) as client:
        snapshot = _data(
            client.post(f"{base}/workspace/sessions", json={"lessonSlug": LESSON})
        )
        session_id = snapshot["sessionId"]
        print(
            f"会话 {session_id}：{len(snapshot['cells'])} 个单元格，"
            f"{len(snapshot['tasks'])} 个任务，数据集 {snapshot['datasets']}"
        )

        for cell_id, code in SOLUTIONS.items():
            snapshot = _data(
                client.put(
                    f"{base}/workspace/sessions/{session_id}/cells/{cell_id}",
                    json={"code": code},
                )
            )

        # 起始格：只读数据并打印形状，必须执行成功
        run = _data(
            client.post(
                f"{base}/workspace/sessions/{session_id}/cells/c1/run",
                json={"requestId": _rid()},
            )
        )
        print(f"c1 执行：{run['verdict']}（{run['durationMs']}ms）")

        failures = 0
        for task_id in TASK_ORDER:
            cell_id = next(
                task["cellId"]
                for task in snapshot["tasks"]
                if task["taskId"] == task_id
            )
            result = _data(
                client.post(
                    f"{base}/workspace/sessions/{session_id}/tasks/{task_id}/submit",
                    json={"requestId": _rid()},
                )
            )
            assertions = ", ".join(
                f"{item['id']}={item['status']}" for item in result["assertions"]
            )
            print(
                f"{task_id}（{cell_id}）提交：{result['verdict']}"
                f" → 任务状态 {result['taskStatus']} [{assertions}]"
            )
            if result["verdict"] != "passed":
                failures += 1
                for item in result["assertions"]:
                    if item["status"] != "passed":
                        print(f"  失败 {item['id']}：{item['actual'] or item['detail']}")

        snapshot = _data(
            client.get(f"{base}/workspace/sessions/{session_id}")
        )
        statuses = {task["taskId"]: task["status"] for task in snapshot["tasks"]}
        print(f"任务状态：{statuses}")

    if failures:
        print(f"失败：{failures} 个任务未通过")
        return 1
    print("工作区自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())