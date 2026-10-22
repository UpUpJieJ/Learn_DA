"""学习进度与学习报告（改版 P1/P3）。

数据源只有一张表：``task_attempts``（任务提交记录）。进度按「每门课任务数 vs 已通过任务数」
计算，报告里额外给出 track 维度能力、失败断言模式与最近提交。

设计约束（设计稿 §15.2）：
* ``/learn`` 课程地图要看清**任务级**进度，所以进度接口返回每课的 ``passedTasks / totalTasks``
  与 ``currentTaskId``（第一个未通过的任务）；
* ``/report`` 只用真实证据计算，没有数据时返回 0 而不是编造的能力雷达。
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_catalog import get_content_index

from .content import WorkspaceSpec, load_workspace
from .models import TaskAttempt

RECENT_LIMIT = 12
ERROR_PATTERN_LIMIT = 8


def _specs() -> dict[str, WorkspaceSpec]:
    specs: dict[str, WorkspaceSpec] = {}
    for lesson in get_content_index().lessons:
        spec = load_workspace(lesson)
        if spec is not None:
            specs[str(lesson["slug"])] = spec
    return specs


def _lessons() -> dict[str, dict[str, Any]]:
    return {str(item["slug"]): item for item in get_content_index().lessons}


def _track_labels() -> dict[str, str]:
    catalog = get_content_index().catalog or {}
    return {
        str(track.get("key")): str(track.get("label") or track.get("key"))
        for track in catalog.get("tracks") or []
        if isinstance(track, dict)
    }


async def _attempts(db: AsyncSession, visitor_id: str) -> list[TaskAttempt]:
    stmt = (
        select(TaskAttempt)
        .where(TaskAttempt.visitor_id == visitor_id)
        .order_by(TaskAttempt.created_time, TaskAttempt.id)
    )
    return list((await db.execute(stmt)).scalars().all())


def _latest(attempts: list[TaskAttempt]) -> dict[tuple[str, str], TaskAttempt]:
    latest: dict[tuple[str, str], TaskAttempt] = {}
    for attempt in attempts:
        latest[(attempt.lesson_slug, attempt.task_id)] = attempt
    return latest


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _lesson_progress(
    lessons: dict[str, dict[str, Any]],
    specs: dict[str, WorkspaceSpec],
    latest: dict[tuple[str, str], TaskAttempt],
    counts: dict[str, int],
    last_seen: dict[str, datetime],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slug, spec in specs.items():
        lesson = lessons.get(slug) or {}
        passed = 0
        current: str | None = None
        for task in spec.tasks:
            attempt = latest.get((slug, task.task_id))
            if attempt is not None and attempt.status == "passed":
                passed += 1
            elif current is None:
                current = task.task_id
        total = len(spec.tasks)
        if passed == 0 and counts.get(slug, 0) == 0:
            status = "not_started"
        elif total and passed >= total:
            status = "completed"
        else:
            status = "in_progress"
        rows.append(
            {
                "lessonSlug": slug,
                "title": lesson.get("title") or slug,
                "track": lesson.get("track"),
                "order": lesson.get("order") or 0,
                "difficulty": lesson.get("difficulty"),
                "estimatedMinutes": lesson.get("estimated_minutes"),
                "totalTasks": total,
                "passedTasks": passed,
                "status": status,
                "currentTaskId": current,
                "attempts": counts.get(slug, 0),
                "lastActivityAt": _iso(last_seen.get(slug)),
            }
        )
    rows.sort(key=lambda row: (row["order"], row["lessonSlug"]))
    return rows


def _streak(days: list[date]) -> int:
    """从最近一天往回数连续天数（今天或昨天都能起算，隔一天就断）。"""
    if not days:
        return 0
    ordered = sorted(set(days), reverse=True)
    today = datetime.now(timezone.utc).date()
    if (today - ordered[0]).days > 1:
        return 0
    streak = 1
    for previous, current in zip(ordered, ordered[1:]):
        if (previous - current).days == 1:
            streak += 1
        else:
            break
    return streak


def _error_patterns(
    attempts: list[TaskAttempt],
    lessons: dict[str, dict[str, Any]],
    specs: dict[str, WorkspaceSpec],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for attempt in attempts:
        if attempt.status == "passed":
            continue
        try:
            results = json.loads(attempt.assertions or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(results, list):
            continue
        lesson = lessons.get(attempt.lesson_slug) or {}
        task_title = attempt.task_id
        spec = specs.get(attempt.lesson_slug)
        if spec is not None:
            task = next(
                (item for item in spec.tasks if item.task_id == attempt.task_id), None
            )
            if task is not None:
                task_title = task.title
        for item in results:
            if not isinstance(item, dict) or item.get("status") == "passed":
                continue
            assertion_id = str(item.get("id") or "")
            key = (attempt.lesson_slug, attempt.task_id, assertion_id)
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "lessonSlug": attempt.lesson_slug,
                    "lessonTitle": lesson.get("title") or attempt.lesson_slug,
                    "taskId": attempt.task_id,
                    "taskTitle": task_title,
                    "assertionId": assertion_id,
                    "title": str(item.get("title") or assertion_id),
                    "status": str(item.get("status") or "failed"),
                    "count": 0,
                    "lastActual": "",
                }
                buckets[key] = bucket
            bucket["count"] += 1
            actual = str(item.get("actual") or item.get("detail") or "")
            if actual:
                bucket["lastActual"] = actual[:200]
    rows = sorted(buckets.values(), key=lambda row: (-row["count"], row["assertionId"]))
    return rows[:ERROR_PATTERN_LIMIT]


async def lesson_progress(db: AsyncSession, visitor_id: str) -> dict[str, Any]:
    """课程地图用：每门课的 task 级进度 + 汇总。"""
    specs = _specs()
    lessons = _lessons()
    attempts = await _attempts(db, visitor_id)
    latest = _latest(attempts)

    counts: dict[str, int] = defaultdict(int)
    last_seen: dict[str, datetime] = {}
    for attempt in attempts:
        counts[attempt.lesson_slug] += 1
        if attempt.created_time is not None:
            last_seen[attempt.lesson_slug] = attempt.created_time

    rows = _lesson_progress(lessons, specs, latest, counts, last_seen)
    started = [row for row in rows if row["status"] != "not_started"]
    completed = [row for row in rows if row["status"] == "completed"]

    track_labels = _track_labels()
    tracks: list[dict[str, Any]] = []
    for row in rows:
        track = str(row["track"] or "other")
        entry = next((item for item in tracks if item["track"] == track), None)
        if entry is None:
            entry = {
                "track": track,
                "label": track_labels.get(track, track),
                "totalTasks": 0,
                "passedTasks": 0,
                "lessons": 0,
                "completedLessons": 0,
            }
            tracks.append(entry)
        entry["totalTasks"] += row["totalTasks"]
        entry["passedTasks"] += row["passedTasks"]
        entry["lessons"] += 1
        if row["status"] == "completed":
            entry["completedLessons"] += 1

    return {
        "lessons": rows,
        "tracks": tracks,
        "summary": {
            "lessonsTotal": len(rows),
            "lessonsStarted": len(started),
            "lessonsCompleted": len(completed),
            "tasksTotal": sum(row["totalTasks"] for row in rows),
            "tasksPassed": sum(row["passedTasks"] for row in rows),
            "attemptsTotal": len(attempts),
        },
    }


async def learning_report(db: AsyncSession, visitor_id: str) -> dict[str, Any]:
    """学习报告用：真实能力、失败模式与最近提交。"""
    specs = _specs()
    lessons = _lessons()
    attempts = await _attempts(db, visitor_id)
    latest = _latest(attempts)

    counts: dict[str, int] = defaultdict(int)
    last_seen: dict[str, datetime] = {}
    days: list[date] = []
    passed_attempts = 0
    for attempt in attempts:
        counts[attempt.lesson_slug] += 1
        if attempt.status == "passed":
            passed_attempts += 1
        if attempt.created_time is not None:
            last_seen[attempt.lesson_slug] = attempt.created_time
            stamp = attempt.created_time
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            days.append(stamp.astimezone(timezone.utc).date())

    rows = _lesson_progress(lessons, specs, latest, counts, last_seen)
    track_labels = _track_labels()
    track_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        track = str(row["track"] or "other")
        entry = track_rows.setdefault(
            track,
            {
                "track": track,
                "label": track_labels.get(track, track),
                "totalTasks": 0,
                "passedTasks": 0,
                "lessons": 0,
                "completedLessons": 0,
            },
        )
        entry["totalTasks"] += row["totalTasks"]
        entry["passedTasks"] += row["passedTasks"]
        entry["lessons"] += 1
        if row["status"] == "completed":
            entry["completedLessons"] += 1

    for entry in track_rows.values():
        total = entry["totalTasks"]
        entry["ratio"] = round(entry["passedTasks"] / total, 3) if total else 0.0

    recent: list[dict[str, Any]] = []
    for attempt in reversed(attempts[-RECENT_LIMIT:]):
        lesson = lessons.get(attempt.lesson_slug) or {}
        spec = specs.get(attempt.lesson_slug)
        task_title = attempt.task_id
        if spec is not None:
            task = next(
                (item for item in spec.tasks if item.task_id == attempt.task_id), None
            )
            if task is not None:
                task_title = task.title
        recent.append(
            {
                "lessonSlug": attempt.lesson_slug,
                "lessonTitle": lesson.get("title") or attempt.lesson_slug,
                "taskId": attempt.task_id,
                "taskTitle": task_title,
                "status": attempt.status,
                "attemptNo": attempt.attempt_no,
                "createdAt": _iso(attempt.created_time),
            }
        )

    first_try = 0
    seen: set[tuple[str, str]] = set()
    for attempt in attempts:  # 升序遍历：某任务第一次提交就通过 = 一次过
        key = (attempt.lesson_slug, attempt.task_id)
        if key in seen:
            continue
        seen.add(key)
        if attempt.status == "passed":
            first_try += 1

    today = datetime.now(timezone.utc).date()
    return {
        "lessonProgress": rows,
        "tracks": sorted(track_rows.values(), key=lambda row: row["track"]),
        "summary": {
            "lessonsTotal": len(rows),
            "lessonsStarted": sum(1 for row in rows if row["status"] != "not_started"),
            "lessonsCompleted": sum(1 for row in rows if row["status"] == "completed"),
            "tasksTotal": sum(row["totalTasks"] for row in rows),
            "tasksPassed": sum(row["passedTasks"] for row in rows),
            "attemptsTotal": len(attempts),
            "tasksFirstTry": first_try,
            "activeDays": len(set(days)),
            "streakDays": _streak(days),
            "lastActiveAt": _iso(max(last_seen.values()) if last_seen else None),
            "daysSinceActive": (today - max(days)).days if days else None,
        },
        "errorPatterns": _error_patterns(attempts, lessons, specs),
        "recent": recent,
        "windowDays": (today - min(days)).days + 1 if days else 0,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
