"""Persist current task validation independently from execution success.

Revision ID: d8a42b6f9013
Revises: c7d31a8e9f02

Existing live cells deliberately default to unverified. Their historical
TaskAttempts remain untouched; one successful task resubmission is required
to establish validation for the currently stored code and upstream prefix.
"""
from alembic import op
import sqlalchemy as sa

revision = "d8a42b6f9013"
down_revision = "c7d31a8e9f02"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("session_cells", sa.Column("task_verified", sa.Boolean(),
                  nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table("session_cells") as batch:
        batch.drop_column("task_verified")
