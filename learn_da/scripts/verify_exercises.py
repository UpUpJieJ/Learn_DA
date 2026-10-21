"""End-to-end exercise check: every lesson's starter fails, every solution passes.

This drives the real chain — HTTP API -> Runner -> validator -> ExerciseAttempt —
so it proves the loop works on this host, not just that the unit tests pass.

Usage:
    .venv/Scripts/python.exe scripts/verify_exercises.py
    .venv/Scripts/python.exe scripts/verify_exercises.py --base-url http://127.0.0.1:8000
    .venv/Scripts/python.exe scripts/verify_exercises.py --only polars-basics

Note: it persists ExerciseAttempts for the anonymous session it creates, and the
playground rate limit (10/minute by default) applies — start the API with
RATE_LIMIT_ENABLED=False when checking all 13 lessons in one go.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

import httpx
import yaml

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "lessons"

_COMMENT_LINE = re.compile(r"^[ \t]*#.*\n?", re.MULTILINE)
_EMPTY_EXECUTE = re.compile(r'(result = con\.execute\(""")\s*(""")')


def strip_todo_comments(code: str) -> str:
    """Drop the instructional comments so the snippet is valid SQL/Python."""
    return _COMMENT_LINE.sub("", code)


def _sql(query: str) -> Callable[[str], str]:
    def apply(code: str) -> str:
        return _EMPTY_EXECUTE.sub(lambda m: f"{m.group(1)}\n{query}\n{m.group(2)}", code)

    return apply


def _replace(old: str, new: str) -> Callable[[str], str]:
    def apply(code: str) -> str:
        if old not in code:
            raise SystemExit(f"solution template no longer matches: {old!r}")
        return code.replace(old, new)

    return apply


def _chain(*transforms: Callable[[str], str]) -> Callable[[str], str]:
    def apply(code: str) -> str:
        for transform in transforms:
            code = transform(code)
        return code

    return apply


SOLUTIONS: dict[str, Callable[[str], str]] = {
    "polars-basics": _replace(
        "result = orders",
        'result = orders.filter(pl.col("price") > 100).select("product", "price")',
    ),
    "duckdb-analytics": _sql(
        "SELECT region, COUNT(*) AS cnt, SUM(amount) AS total\n"
        "FROM orders GROUP BY region ORDER BY total DESC"
    ),
    "polars-groupby": _replace(
        "result = sales",
        'result = (\n'
        '    sales.group_by("region")\n'
        '    .agg(pl.sum("amount").alias("total_amount"), pl.len().alias("order_count"))\n'
        '    .sort("total_amount", descending=True)\n'
        ')',
    ),
    "polars-expressions": _replace(
        "result = products",
        'result = products.with_columns(\n'
        '    (pl.col("price") * pl.col("quantity")).alias("revenue"),\n'
        '    pl.when(pl.col("price") >= 500)\n'
        '    .then(pl.lit("高价值"))\n'
        '    .otherwise(pl.lit("普通"))\n'
        '    .alias("price_band"),\n'
        ')',
    ),
    "polars-cleaning": _replace(
        "result = raw",
        'result = (\n'
        '    raw.unique(subset=["user_id"], keep="first")\n'
        '    .with_columns(pl.col("city").fill_null("未知"))\n'
        '    .with_columns(\n'
        '        pl.when(pl.col("age") == "unknown")\n'
        "        .then(None)\n"
        '        .otherwise(pl.col("age"))\n'
        '        .cast(pl.Int32)\n'
        '        .alias("age")\n'
        '    )\n'
        '    .select("user_id", "city", "age")\n'
        ')',
    ),
    "polars-joins": _replace(
        "result = orders",
        'result = (\n'
        '    orders.join(users, on="user_id", how="left")\n'
        '    .join(products, on="product_id", how="left")\n'
        '    .with_columns((pl.col("quantity") * pl.col("unit_price")).alias("amount"))\n'
        '    .select("order_id", "city", "category", "amount")\n'
        ')',
    ),
    "duckdb-sql-foundations": _sql(
        "SELECT category, COUNT(*) AS cnt, SUM(amount) AS total\n"
        "FROM orders GROUP BY category HAVING SUM(amount) > 200 ORDER BY total DESC"
    ),
    "duckdb-joins-cte": _sql(
        "WITH line_items AS (\n"
        "    SELECT o.order_id, o.quantity * p.unit_price AS amount\n"
        "    FROM orders o LEFT JOIN products p ON o.product_id = p.product_id\n"
        ")\n"
        "SELECT order_id, amount FROM line_items WHERE amount > 250 ORDER BY amount DESC"
    ),
    "duckdb-window-functions": _sql(
        "WITH ranked AS (\n"
        "    SELECT order_id, region, amount,\n"
        "           RANK() OVER (PARTITION BY region ORDER BY amount DESC) AS rn\n"
        "    FROM orders\n"
        ")\n"
        "SELECT order_id, region, amount FROM ranked WHERE rn = 1 ORDER BY order_id"
    ),
    "polars-lazy-pipeline": _replace(
        "result = orders",
        'result = (\n'
        '    orders.lazy()\n'
        '    .filter(pl.col("amount") >= 100)\n'
        '    .with_columns(\n'
        '        pl.when(pl.col("amount") >= 500)\n'
        '        .then(pl.lit("大额"))\n'
        '        .otherwise(pl.lit("普通"))\n'
        '        .alias("amount_band")\n'
        '    )\n'
        '    .select("order_id", "amount", "amount_band")\n'
        '    .collect()\n'
        ')',
    ),
    "polars-duckdb-workflow": _chain(
        _replace(
            "clean_orders = orders",
            'clean_orders = orders.with_columns(pl.col("region").fill_null("未知"))',
        ),
        _replace(
            "con = duckdb.connect()",
            'con = duckdb.connect()\n'
            'con.register("clean_orders", clean_orders.to_arrow())',
        ),
        _sql(
            'SELECT region, SUM(amount) AS total FROM clean_orders\n'
            'GROUP BY region ORDER BY total DESC'
        ),
    ),
    "python-functions": _replace("    pass", "    return score + 5"),
    "python-collections": _chain(
        _replace("    pass", "    return score * 2"),
        lambda code: code.rstrip()
        + "\n\nfor score in scores:\n    print(double_score(score))\n",
    ),
}


def load_exercises() -> list[dict]:
    exercises = []
    for path in sorted(CONTENT_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        frontmatter = text.split("---")[1]
        data = yaml.safe_load(frontmatter)
        exercise = data.get("exercise")
        if not exercise:
            continue
        exercises.append(
            {
                "slug": data["slug"],
                "title": data["title"],
                "exercise_id": exercise["id"],
                "language": exercise.get("language", "python"),
                "starter": exercise["starter_code"],
                "validator": (exercise.get("validator") or {}).get("type"),
            }
        )
    return exercises


def _verification_status(result: dict) -> str | None:
    verification = result.get("verification") or {}
    return verification.get("status")


def submit(client: httpx.Client, base_url: str, exercise: dict, code: str) -> dict:
    response = client.post(
        f"{base_url}/api/v1/playground/execute",
        json={
            "code": code,
            "language": exercise["language"],
            "lessonSlug": exercise["slug"],
            "exerciseId": exercise["exercise_id"],
        },
        timeout=60.0,
    )
    if response.status_code == 429:
        raise SystemExit(
            "rate limited (429): restart the API with RATE_LIMIT_ENABLED=False"
        )
    response.raise_for_status()
    return response.json()["data"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--only", default=None, help="check a single lesson slug")
    args = parser.parse_args()

    exercises = load_exercises()
    if args.only:
        exercises = [e for e in exercises if e["slug"] == args.only]
    if not exercises:
        print("no exercises found")
        return 1

    failures: list[str] = []
    with httpx.Client(follow_redirects=True) as client:
        # Establish the anonymous visitor session before submitting anything.
        client.get(f"{args.base_url}/api/v1/catalog", timeout=30.0)

        print(f"{'lesson':<28} {'validator':<16} {'starter':<9} {'solution':<15} attempt")
        print("-" * 84)

        for exercise in exercises:
            solution_builder = SOLUTIONS.get(exercise["slug"])
            if solution_builder is None:
                failures.append(f"{exercise['slug']}: no solution template")
                print(f"{exercise['slug']:<28} MISSING SOLUTION TEMPLATE")
                continue

            starter_code = strip_todo_comments(exercise["starter"])
            solution_code = solution_builder(starter_code)

            starter_result = submit(client, args.base_url, exercise, starter_code)
            solution_result = submit(client, args.base_url, exercise, solution_code)

            starter_passed = _verification_status(starter_result) == "passed"
            solution_status = _verification_status(solution_result)
            solution_passed = solution_status == "passed"
            attempt_id = solution_result.get("attemptId")

            marker_starter = "pass" if starter_passed else "fail"
            marker_solution = solution_status or "no-verification"
            print(
                f"{exercise['slug']:<28} {str(exercise['validator']):<16} "
                f"{marker_starter:<9} {marker_solution:<15} {attempt_id}"
            )

            if starter_passed:
                failures.append(
                    f"{exercise['slug']}: starter code passed the validator")
            if not solution_passed:
                detail = (solution_result.get("verification") or {}).get(
                    "failureReason")
                stderr = (solution_result.get("stderr") or "")[:300]
                failures.append(
                    f"{exercise['slug']}: solution rejected ({detail}) {stderr}")
            if not attempt_id:
                failures.append(f"{exercise['slug']}: no ExerciseAttempt persisted")

    print("-" * 84)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"OK: {len(exercises)} exercises verified (starter rejected, solution accepted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())