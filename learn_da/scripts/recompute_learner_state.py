"""阶段 1 §5.4：一次性重算 learner_lesson_progress 投影

从 ``learning_records`` 事件流重放推导每个 (visitor_id, lesson_slug) 的权威状态，
upsert 到 ``learner_lesson_progress``，并对重复完成事件去重。

设计原则（与路线图一致）：
- 相同事件重放不改变最终投影：按 created_time 顺序回放 complete/uncomplete/code_run，
  最终状态只取决于事件序列，不依赖事件数量。
- 完成状态由 complete/uncomplete 序列的最后一个决定，避免历史重复完成污染投影。
- code_run 的 success/error 计数依据 ``status`` 字段；缺失时按 success 计。

用法::

    uv run python scripts/recompute_learner_state.py            # 干跑，只打印审计结果
    uv run python scripts/recompute_learner_state.py --write    # 实际写入

迁移已有数据后应执行一次；后续正常写入路径已保证幂等，无需重复运行。
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select

from app.analytics.models import LearningRecord
from app.core.database.database import AsyncSessionLocal
from app.learner_state.models import LearnerLessonProgress

# 状态机：当前状态 + 事件 -> 新状态
# 只关心 complete / uncomplete 两个事件对完成态的影响
_COMPLETION_TRANSITIONS = {
    ("started", "lesson_complete"): "completed",
    ("completed", "lesson_complete"): "completed",  # 幂等
    ("uncompleted", "lesson_complete"): "completed",
    ("started", "lesson_uncomplete"): "uncompleted",
    ("completed", "lesson_uncomplete"): "uncompleted",
    ("uncompleted", "lesson_uncomplete"): "uncompleted",  # 幂等
}


def _derive_state(records: list[LearningRecord]) -> dict:
    """回放一组事件，推导最终投影。"""
    state = "started"
    completed_at: datetime | None = None
    last_activity_at: datetime | None = None
    attempt_count = 0
    success_count = 0
    error_count = 0

    for rec in sorted(
        records,
        key=lambda r: r.created_time or datetime.min.replace(tzinfo=timezone.utc),
    ):
        created = rec.created_time
        if created and (last_activity_at is None or created > last_activity_at):
            last_activity_at = created

        event_type = rec.event_type
        new_state = _COMPLETION_TRANSITIONS.get((state, event_type))
        if new_state is not None:
            state = new_state
            if new_state == "completed":
                completed_at = created
            else:
                completed_at = None
        elif event_type == "code_run":
            attempt_count += 1
            status = (rec.status or "success").lower()
            if status == "success":
                success_count += 1
            else:
                # error / timeout / rejected / unavailable 都计入失败侧
                error_count += 1

    return {
        "status": state,
        "completed_at": completed_at,
        "last_activity_at": last_activity_at,
        "attempt_count": attempt_count,
        "success_count": success_count,
        "error_count": error_count,
    }


async def recompute(*, write: bool = False, session=None) -> dict:
    """重算并（可选）写入。返回审计摘要。

    传入 ``session`` 时使用该会话（用于测试）；否则使用应用默认数据库会话。
    """
    owns_session = session is None
    if owns_session:
        session = AsyncSessionLocal()
    try:
        stmt = (
            select(LearningRecord)
            .where(LearningRecord.is_deleted == False)  # noqa: E712
            .order_by(
                LearningRecord.visitor_id,
                LearningRecord.lesson_slug,
                LearningRecord.created_time,
            )
        )
        result = await session.execute(stmt)
        records = list(result.scalars().all())

        # 按 (visitor_id, lesson_slug) 分组
        groups: dict[tuple[str, str], list[LearningRecord]] = defaultdict(list)
        for rec in records:
            if not rec.lesson_slug:
                continue
            groups[(rec.visitor_id, rec.lesson_slug)].append(rec)

        # 先读取已有 progress 行，用于 upsert
        existing_stmt = select(LearnerLessonProgress).where(
            LearnerLessonProgress.is_deleted == False  # noqa: E712
        )
        existing_result = await session.execute(existing_stmt)
        existing_map: dict[tuple[str, str], LearnerLessonProgress] = {
            (row.visitor_id, row.lesson_slug): row
            for row in existing_result.scalars().all()
        }

        audit = {
            "total_events": len(records),
            "groups": len(groups),
            "upserted": 0,
            "unchanged": 0,
            "details": [],
        }

        for (visitor_id, lesson_slug), group_records in groups.items():
            derived = _derive_state(group_records)
            row = existing_map.get((visitor_id, lesson_slug))
            if row is None:
                row = LearnerLessonProgress(
                    visitor_id=visitor_id,
                    lesson_slug=lesson_slug,
                )
                session.add(row)
            audit["upserted"] += 1

            row.status = derived["status"]
            row.completed_at = derived["completed_at"]
            row.last_activity_at = derived["last_activity_at"]
            row.attempt_count = derived["attempt_count"]
            row.success_count = derived["success_count"]
            row.error_count = derived["error_count"]

            audit["details"].append(
                {
                    "visitor_id": visitor_id,
                    "lesson_slug": lesson_slug,
                    **derived,
                }
            )

        if write:
            await session.commit()
            audit["committed"] = True
        else:
            audit["committed"] = False

        return audit
    finally:
        if owns_session:
            await session.close()


def _format_audit(audit: dict) -> str:
    lines = [
        f"事件总数: {audit['total_events']}",
        f"(visitor, lesson) 分组数: {audit['groups']}",
        f"upsert 行数: {audit['upserted']}",
        f"已提交: {audit['committed']}",
        "",
        "明细 (最多展示前 20 条):",
    ]
    for d in audit["details"][:20]:
        completed = (
            d["completed_at"].strftime("%Y-%m-%d %H:%M:%S")
            if d["completed_at"]
            else "-"
        )
        lines.append(
            f"  {d['visitor_id']} / {d['lesson_slug']}: "
            f"status={d['status']} attempts={d['attempt_count']} "
            f"success={d['success_count']} error={d['error_count']} completed_at={completed}"
        )
    if len(audit["details"]) > 20:
        lines.append(f"  ... 共 {len(audit['details'])} 条")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="重算 learner_lesson_progress 投影")
    parser.add_argument(
        "--write",
        action="store_true",
        help="实际写入数据库（默认仅干跑打印审计结果）",
    )
    args = parser.parse_args()

    audit = asyncio.run(recompute(write=args.write))
    print(_format_audit(audit))
    if not args.write:
        print("\n干跑模式：未写入。添加 --write 实际写入。")


if __name__ == "__main__":
    main()
