"""Verify all workspace contracts through a live Docker Runner and API judgement.

Run with --runner-url http://127.0.0.1:8080 and RUNNER_TOKEN set. Creates only
ephemeral sandbox containers: no learner database, attempts or production writes.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.content_loader import load_lesson_from_file
from app.sandbox.client import RunnerClient
from app.workspace.content import dataset_payload, load_workspace, refs_payload
from scripts.workspace_solutions import SOLUTIONS


async def verify(url: str) -> int:
    config = SimpleNamespace(RUNNER_URL=url, RUNNER_TOKEN=os.environ.get("RUNNER_TOKEN", ""),
                             RUNNER_TIMEOUT_SECONDS=30, RUNNER_SESSION_TIMEOUT_SECONDS=40)
    passed = total = 0
    async with httpx.AsyncClient() as http:
        client = RunnerClient(http, config)
        if not await client.is_ready():
            raise RuntimeError("Runner is not ready")
        for path in sorted((ROOT / "content" / "lessons").glob("*.md")):
            lesson = load_lesson_from_file(path)
            spec = load_workspace(lesson)
            for task in spec.tasks:
                for label, solutions in (("starter", {}), ("solution", SOLUTIONS[spec.lesson_slug])):
                    payload = {"requestId": str(uuid.uuid4()), "stopAt": task.cell_id,
                               "cells": [{"cellId": c.cell_id, "code": solutions.get(c.cell_id, c.code),
                                          "language": c.language} for c in spec.cells],
                               "datasets": dataset_payload(spec.datasets),
                               "refs": refs_payload(spec.ref_names()),
                               "assertions": spec.assertions_for_cell(task.cell_id)}
                    result = await client.execute_session(payload)
                    ok = ((result.get("verdict") == "passed") if label == "solution"
                          else result.get("verdict") in ("assertion_failed", "execution_failed"))
                    # Infrastructure failure is never evidence of a correctly failing starter.
                    ok = ok and result.get("status") == "success" and not result.get("errorType")
                    total += 1
                    passed += int(ok)
                    print(f"{'PASS' if ok else 'FAIL'} {spec.lesson_slug}/{task.task_id}/{label}: {result.get('verdict')}", flush=True)
                    if not ok:
                        print({"errorType": result.get("errorType"), "error": result.get("error"),
                               "assertions": [a for a in result.get("assertions", []) if a.get("status") != "passed"],
                               "cells": [c for c in result.get("cells", []) if c.get("status") == "error"]}, flush=True)
        print(f"Docker observation contracts: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(verify(args.runner_url)))
