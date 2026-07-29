"""agent_embeddings cache table

Revision ID: b7e2a9c4d1f0
Revises: a1b2c3d4e5f6
Create Date: 2026-07-28 12:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2a9c4d1f0'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('agent_embeddings',
        sa.Column('chunk_hash', sa.String(length=64), nullable=False, comment='sha256(model + chunk 文本)'),
        sa.Column('model', sa.String(length=128), nullable=False, comment='embedding 模型名'),
        sa.Column('dimension', sa.Integer(), nullable=True, comment='向量维度'),
        sa.Column('vector_json', sa.Text(), nullable=False, comment='向量 JSON 数组'),
        sa.Column('id', sa.Integer(), nullable=False, comment='主键'),
        sa.Column('created_time', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True, comment='创建时间'),
        sa.Column('updated_time', sa.DateTime(timezone=True), nullable=True, comment='更新时间'),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, comment='逻辑删除'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_embeddings_id'), 'agent_embeddings', ['id'], unique=False)
    op.create_index(op.f('ix_agent_embeddings_chunk_hash'), 'agent_embeddings', ['chunk_hash'], unique=True)
    op.create_index(op.f('ix_agent_embeddings_model'), 'agent_embeddings', ['model'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_embeddings_model'), table_name='agent_embeddings')
    op.drop_index(op.f('ix_agent_embeddings_chunk_hash'), table_name='agent_embeddings')
    op.drop_index(op.f('ix_agent_embeddings_id'), table_name='agent_embeddings')
    op.drop_table('agent_embeddings')
