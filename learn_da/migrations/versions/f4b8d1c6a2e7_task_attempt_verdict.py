"""task_attempts 增加 verdict 列

Revision ID: f4b8d1c6a2e7
Revises: a7d1e4f2b9c3
Create Date: 2026-10-23

Agent 证据解析需要区分「代码执行失败」与「断言未通过」。``status`` 只有
passed/failed/skipped 三态，是教学口径；``verdict`` 保留 Runner 原始结论
（passed / assertion_failed / execution_failed）。

历史行按 ``status`` 回填保守值：
- passed  -> passed
- skipped -> execution_failed（断言未求值，多为前面单元格执行失败）
- failed  -> assertion_failed（无法区分执行失败，取更常见的断言失败）
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4b8d1c6a2e7"
down_revision = "a7d1e4f2b9c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_attempts",
        sa.Column("verdict", sa.String(length=24), nullable=True),
    )
    op.execute(
        """
        UPDATE task_attempts
        SET verdict = CASE status
            WHEN 'passed' THEN 'passed'
            WHEN 'skipped' THEN 'execution_failed'
            ELSE 'assertion_failed'
        END
        WHERE verdict IS NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("task_attempts") as batch_op:
        batch_op.drop_column("verdict")