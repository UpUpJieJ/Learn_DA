"""phase1_learner_state

Revision ID: a1b2c3d4e5f6
Revises: 92845c146ce6
Create Date: 2026-07-20 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '92845c146ce6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 创建 learner_lesson_progress 表
    op.create_table('learner_lesson_progress',
        sa.Column('visitor_id', sa.String(length=64), nullable=False, comment='访客 ID'),
        sa.Column('lesson_slug', sa.String(length=128), nullable=False, comment='课程 slug'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='started', comment='状态: started / completed / uncompleted'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='完成时间'),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True, comment='最近活动时间'),
        sa.Column('attempt_count', sa.Integer(), nullable=True, server_default='0', comment='代码尝试次数'),
        sa.Column('success_count', sa.Integer(), nullable=True, server_default='0', comment='成功次数'),
        sa.Column('error_count', sa.Integer(), nullable=True, server_default='0', comment='失败次数'),
        sa.Column('id', sa.Integer(), nullable=False, comment='主键'),
        sa.Column('created_time', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='创建时间'),
        sa.Column('updated_time', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, comment='逻辑删除'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('visitor_id', 'lesson_slug', name='uq_visitor_lesson'),
    )
    op.create_index(op.f('ix_learner_lesson_progress_id'), 'learner_lesson_progress', ['id'], unique=False)
    op.create_index(op.f('ix_learner_lesson_progress_visitor_id'), 'learner_lesson_progress', ['visitor_id'], unique=False)
    op.create_index('idx_llp_visitor_status', 'learner_lesson_progress', ['visitor_id', 'status'], unique=False)

    # 2. 创建 recommendation_cooldowns 表
    op.create_table('recommendation_cooldowns',
        sa.Column('visitor_id', sa.String(length=64), nullable=False, comment='访客 ID'),
        sa.Column('lesson_slug', sa.String(length=128), nullable=False, comment='课程 slug'),
        sa.Column('cooldown_until', sa.DateTime(timezone=True), nullable=False, comment='冷却截止时间'),
        sa.Column('id', sa.Integer(), nullable=False, comment='主键'),
        sa.Column('created_time', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='创建时间'),
        sa.Column('updated_time', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, comment='逻辑删除'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('visitor_id', 'lesson_slug', name='uq_cd_visitor_lesson'),
    )
    op.create_index(op.f('ix_recommendation_cooldowns_id'), 'recommendation_cooldowns', ['id'], unique=False)
    op.create_index(op.f('ix_recommendation_cooldowns_visitor_id'), 'recommendation_cooldowns', ['visitor_id'], unique=False)

    # 3. 为 learning_records 添加新字段
    op.add_column('learning_records', sa.Column('event_id', sa.String(length=64), nullable=True, comment='幂等键（前端生成 UUID）'))
    op.add_column('learning_records', sa.Column('status', sa.String(length=20), nullable=True, comment='执行结果: success / error / timeout / rejected'))
    op.add_column('learning_records', sa.Column('metadata_json', sa.Text(), nullable=True, comment='可选扩展元数据 JSON'))
    op.create_index(op.f('ix_learning_records_event_id'), 'learning_records', ['event_id'], unique=True)

    # 4. 数据迁移：从历史事件回填 learner_lesson_progress
    #
    # 完成状态取每个 (visitor_id, lesson_slug) 上**最后一条** complete/uncomplete
    # 事件决定，而不是"出现过 lesson_complete 就算完成" —— 否则完成后又撤销的课
    # 会被错误回填成 completed。
    #
    # 布尔值用 true/false 字面量而非 0/1，以便 SQLite 之外的方言（PostgreSQL）
    # 也能执行。
    bind = op.get_bind()
    is_deleted_false = sa.false()

    last_events = (
        sa.select(
            sa.column("visitor_id"),
            sa.column("lesson_slug"),
            sa.column("event_type"),
            sa.column("created_time"),
            sa.func.row_number()
            .over(
                partition_by=[sa.column("visitor_id"), sa.column("lesson_slug")],
                order_by=sa.column("created_time").desc(),
            )
            .label("rn"),
        )
        .select_from(sa.table("learning_records"))
        .where(
            sa.column("event_type").in_(("lesson_complete", "lesson_uncomplete")),
            sa.column("lesson_slug").isnot(None),
            sa.or_(
                sa.column("is_deleted").is_(None),
                sa.column("is_deleted") == is_deleted_false,
            ),
        )
        .subquery("last_events")
    )

    completed = (
        sa.select(
            last_events.c.visitor_id,
            last_events.c.lesson_slug,
            sa.literal("completed"),
            last_events.c.created_time,
            last_events.c.created_time,
            sa.literal(0),
            sa.literal(0),
            sa.literal(0),
            sa.func.current_timestamp(),
            is_deleted_false,
        )
        .where(
            last_events.c.rn == 1,
            last_events.c.event_type == "lesson_complete",
        )
    )

    bind.execute(
        sa.insert(
            sa.table(
                "learner_lesson_progress",
                sa.column("visitor_id"),
                sa.column("lesson_slug"),
                sa.column("status"),
                sa.column("completed_at"),
                sa.column("last_activity_at"),
                sa.column("attempt_count"),
                sa.column("success_count"),
                sa.column("error_count"),
                sa.column("created_time"),
                sa.column("is_deleted"),
            )
        ).from_select(
            [
                "visitor_id",
                "lesson_slug",
                "status",
                "completed_at",
                "last_activity_at",
                "attempt_count",
                "success_count",
                "error_count",
                "created_time",
                "is_deleted",
            ],
            completed,
        )
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_learning_records_event_id'), table_name='learning_records')
    op.drop_column('learning_records', 'metadata_json')
    op.drop_column('learning_records', 'status')
    op.drop_column('learning_records', 'event_id')
    op.drop_index(op.f('ix_recommendation_cooldowns_visitor_id'), table_name='recommendation_cooldowns')
    op.drop_index(op.f('ix_recommendation_cooldowns_id'), table_name='recommendation_cooldowns')
    op.drop_table('recommendation_cooldowns')
    op.drop_index('idx_llp_visitor_status', table_name='learner_lesson_progress')
    op.drop_index(op.f('ix_learner_lesson_progress_visitor_id'), table_name='learner_lesson_progress')
    op.drop_index(op.f('ix_learner_lesson_progress_id'), table_name='learner_lesson_progress')
    op.drop_table('learner_lesson_progress')
