"""Agent 模块数据模型。

AgentEmbedding: 课程知识块 embedding 持久化缓存（阶段 ① Task 1.2）。
缓存键为 sha256(model + chunk 文本)，内容或模型变化自动失效。
"""

from sqlalchemy import Column, Integer, String, Text

from app.core.database.base import BaseModel


class AgentEmbedding(BaseModel):
    """课程知识块 embedding 缓存（按内容哈希幂等）"""

    __tablename__ = "agent_embeddings"

    chunk_hash = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="sha256(model + chunk 文本)",
    )
    model = Column(String(128), nullable=False, index=True, comment="embedding 模型名")
    dimension = Column(Integer, nullable=True, comment="向量维度")
    vector_json = Column(Text, nullable=False, comment="向量 JSON 数组")
