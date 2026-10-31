"""Persist idempotent hint responses.

Revision ID: c7d31a8e9f02
Revises: b9c2e5a17f03
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d31a8e9f02"
down_revision = "b9c2e5a17f03"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("hint_usages") as batch:
        batch.add_column(sa.Column("request_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("response", sa.Text(), nullable=True))
        batch.create_unique_constraint("uq_hint_visitor_request", ["visitor_id", "request_id"])


def downgrade():
    with op.batch_alter_table("hint_usages") as batch:
        batch.drop_constraint("uq_hint_visitor_request", type_="unique")
        batch.drop_column("response")
        batch.drop_column("request_id")
