"""phase3_agent_interactions

Revision ID: c3f8a1b7e2d4
Revises: 2e532d3dd383
Create Date: 2026-07-31 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f8a1b7e2d4"
down_revision: Union[str, Sequence[str], None] = "2e532d3dd383"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_interactions",
        sa.Column(
            "request_id",
            sa.String(length=64),
            nullable=False,
            comment="请求幂等键（同 ID 重放不重复创建）",
        ),
        sa.Column(
            "visitor_id",
            sa.String(length=64),
            nullable=False,
            comment="服务端匿名 visitor ID",
        ),
        sa.Column(
            "lesson_slug",
            sa.String(length=128),
            nullable=True,
            comment="证据课程 slug",
        ),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            nullable=True,
            comment="证据 attempt ID",
        ),
        sa.Column(
            "route",
            sa.String(length=64),
            nullable=True,
            comment="意图路由 / FC 工具名",
        ),
        sa.Column(
            "retrieval_mode",
            sa.String(length=32),
            nullable=True,
            comment="检索模式 keyword/embedding",
        ),
        sa.Column(
            "tool_names",
            sa.Text(),
            nullable=True,
            comment="调用的工具名 JSON 数组",
        ),
        sa.Column(
            "llm_latency_ms",
            sa.Integer(),
            nullable=True,
            comment="LLM 总延迟毫秒",
        ),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            nullable=True,
            comment="prompt token 数",
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            nullable=True,
            comment="completion token 数",
        ),
        sa.Column(
            "fallback_reason",
            sa.String(length=64),
            nullable=True,
            comment="降级原因",
        ),
        sa.Column(
            "evidence_state",
            sa.String(length=32),
            nullable=True,
            comment="证据五态",
        ),
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=True,
            comment="验证状态",
        ),
        sa.Column(
            "hint_level",
            sa.Integer(),
            nullable=True,
            comment="提示层级 1-3",
        ),
        sa.Column(
            "next_action",
            sa.String(length=32),
            nullable=True,
            comment="下一步动作",
        ),
        sa.Column(
            "feedback",
            sa.String(length=32),
            nullable=True,
            comment="用户反馈 helpful/not_helpful",
        ),
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column(
            "created_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
            comment="创建时间",
        ),
        sa.Column(
            "updated_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="更新时间",
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=True, comment="逻辑删除"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_agent_interaction_request"),
    )
    op.create_index(
        "idx_ai_visitor_lesson",
        "agent_interactions",
        ["visitor_id", "lesson_slug"],
        unique=False,
    )
    op.create_index(
        "idx_ai_visitor_created",
        "agent_interactions",
        ["visitor_id", "created_time"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_interactions_id"),
        "agent_interactions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_interactions_visitor_id"),
        "agent_interactions",
        ["visitor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_interactions_request_id"),
        "agent_interactions",
        ["request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_interactions_request_id"), table_name="agent_interactions"
    )
    op.drop_index(
        op.f("ix_agent_interactions_visitor_id"), table_name="agent_interactions"
    )
    op.drop_index(op.f("ix_agent_interactions_id"), table_name="agent_interactions")
    op.drop_index("idx_ai_visitor_created", table_name="agent_interactions")
    op.drop_index("idx_ai_visitor_lesson", table_name="agent_interactions")
    op.drop_table("agent_interactions")
