"""hint_usages 表：分级提示发放记录（改版 E2 ladder）

Revision ID: b9c2e5a17f03
Revises: f4b8d1c6a2e7
Create Date: 2026-10-25

层级公式改成按**真实失败次数**计算后（设计稿 §8.2），需要一张表记录
「这个任务已经给到第几层」，否则只能退回按提问次数估算——那会把
「连问几个概念问题」的人直接抬到 L3，而真正连续失败的人永远停在 L1。

历史数据不回填：改版前没有任何提示发放记录，``agent_interactions.hint_level``
是按提问次数算出的估算值，不能当作「已发放层级」的证据。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b9c2e5a17f03"
down_revision = "f4b8d1c6a2e7"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), primary_key=True, index=True, comment="主键"),
        sa.Column(
            "created_time",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment="创建时间",
        ),
        sa.Column("updated_time", sa.DateTime(timezone=True), comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), default=False, comment="逻辑删除"),
    ]


def upgrade() -> None:
    op.create_table(
        "hint_usages",
        *_base_columns(),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("lesson_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("visitor_id", sa.String(64), nullable=False),
        sa.Column("lesson_slug", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failures_at_hint", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_hint_usages_visitor_id", "hint_usages", ["visitor_id"])
    op.create_index("ix_hint_usages_session_id", "hint_usages", ["session_id"])
    op.create_index("ix_hint_usages_lesson_slug", "hint_usages", ["lesson_slug"])
    op.create_index("ix_hint_usages_task_id", "hint_usages", ["task_id"])
    op.create_index("ix_hint_session_task", "hint_usages", ["session_id", "task_id"])


def downgrade() -> None:
    op.drop_index("ix_hint_session_task", table_name="hint_usages")
    op.drop_index("ix_hint_usages_task_id", table_name="hint_usages")
    op.drop_index("ix_hint_usages_lesson_slug", table_name="hint_usages")
    op.drop_index("ix_hint_usages_session_id", table_name="hint_usages")
    op.drop_index("ix_hint_usages_visitor_id", table_name="hint_usages")
    op.drop_table("hint_usages")
