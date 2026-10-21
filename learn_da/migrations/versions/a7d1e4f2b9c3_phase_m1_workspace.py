"""phase M1: 学习工作区（会话 / 单元格 / 执行事件 / 任务尝试）

Revision ID: a7d1e4f2b9c3
Revises: c3f8a1b7e2d4
Create Date: 2026-10-22 00:20:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7d1e4f2b9c3"
down_revision = "c3f8a1b7e2d4"
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
        "lesson_sessions",
        *_base_columns(),
        sa.Column("visitor_id", sa.String(64), nullable=False),
        sa.Column("lesson_slug", sa.String(64), nullable=False),
        sa.Column("content_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.UniqueConstraint(
            "visitor_id", "lesson_slug", name="uq_session_visitor_lesson"
        ),
    )
    op.create_index(
        "ix_lesson_sessions_visitor_id", "lesson_sessions", ["visitor_id"]
    )
    op.create_index(
        "ix_lesson_sessions_lesson_slug", "lesson_sessions", ["lesson_slug"]
    )

    op.create_table(
        "session_cells",
        *_base_columns(),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("lesson_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cell_id", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="task"),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("language", sa.String(16), nullable=False, server_default="python"),
        sa.Column("code", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="stale"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "cell_id", name="uq_cell_session_cell"),
    )
    op.create_index("ix_session_cells_session_id", "session_cells", ["session_id"])
    op.create_index(
        "ix_cell_session_position", "session_cells", ["session_id", "position"]
    )

    op.create_table(
        "run_events",
        *_base_columns(),
        sa.Column("visitor_id", sa.String(64), nullable=False),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("lesson_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("cell_id", sa.String(64), nullable=False),
        sa.Column("stop_at", sa.String(64), nullable=True),
        sa.Column("verdict", sa.String(24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "visitor_id", "request_id", name="uq_run_visitor_request"
        ),
    )
    op.create_index("ix_run_events_visitor_id", "run_events", ["visitor_id"])
    op.create_index("ix_run_events_session_id", "run_events", ["session_id"])

    op.create_table(
        "task_attempts",
        *_base_columns(),
        sa.Column("visitor_id", sa.String(64), nullable=False),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("lesson_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lesson_slug", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("code", sa.Text(), nullable=False, server_default=""),
        sa.Column("actual", sa.Text(), nullable=False, server_default=""),
        sa.Column("assertions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "is_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_task_attempts_visitor_id", "task_attempts", ["visitor_id"])
    op.create_index("ix_task_attempts_session_id", "task_attempts", ["session_id"])
    op.create_index("ix_task_attempts_lesson_slug", "task_attempts", ["lesson_slug"])
    op.create_index("ix_task_attempts_task_id", "task_attempts", ["task_id"])
    op.create_index(
        "ix_attempt_session_task", "task_attempts", ["session_id", "task_id"]
    )


def downgrade() -> None:
    for index_name in (
        "ix_attempt_session_task",
        "ix_task_attempts_task_id",
        "ix_task_attempts_lesson_slug",
        "ix_task_attempts_session_id",
        "ix_task_attempts_visitor_id",
    ):
        op.drop_index(index_name, table_name="task_attempts")
    op.drop_table("task_attempts")

    for index_name in (
        "ix_run_events_session_id",
        "ix_run_events_visitor_id",
    ):
        op.drop_index(index_name, table_name="run_events")
    op.drop_table("run_events")

    for index_name in ("ix_cell_session_position", "ix_session_cells_session_id"):
        op.drop_index(index_name, table_name="session_cells")
    op.drop_table("session_cells")

    for index_name in (
        "ix_lesson_sessions_lesson_slug",
        "ix_lesson_sessions_visitor_id",
    ):
        op.drop_index(index_name, table_name="lesson_sessions")
    op.drop_table("lesson_sessions")