"""Agent 模块数据模型。

AgentEmbedding: 课程知识块 embedding 持久化缓存（阶段 ① Task 1.2）。
缓存键为 sha256(model + chunk 文本)，内容或模型变化自动失效。

AgentInteraction: 每次 /agent/chat 的交互审计（阶段 3 Task 3）。
request_id 为唯一幂等键，相同 ID 重放不重复创建、不重复计入 ai_help。
不持久化完整 prompt、完整代码、Runner token 或会话 cookie。
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Index, UniqueConstraint

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


class AgentInteraction(BaseModel):
    """Agent 对话交互审计记录（阶段 3 Task 3）。

    用于跨进程查询、统计与回放：从一个 request ID 可追溯用户动作、
    证据、检索、模型成本、反馈与后续验证结果。
    """

    __tablename__ = "agent_interactions"

    # 身份与幂等
    request_id = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="请求幂等键（同 ID 重放不重复创建）",
    )
    visitor_id = Column(
        String(64), nullable=False, index=True, comment="服务端匿名 visitor ID"
    )

    # 证据关联（来自 AgentEvidenceResolver，非客户端自报）
    lesson_slug = Column(String(128), nullable=True, comment="证据课程 slug")
    attempt_id = Column(Integer, nullable=True, comment="证据 attempt ID")

    # 调用与检索指标
    route = Column(String(64), nullable=True, comment="意图路由 / FC 工具名")
    retrieval_mode = Column(String(32), nullable=True, comment="检索模式 keyword/embedding")
    tool_names = Column(Text, nullable=True, comment="调用的工具名 JSON 数组")
    llm_latency_ms = Column(Integer, nullable=True, comment="LLM 总延迟毫秒")
    input_tokens = Column(Integer, nullable=True, comment="prompt token 数")
    output_tokens = Column(Integer, nullable=True, comment="completion token 数")
    fallback_reason = Column(String(64), nullable=True, comment="降级原因")

    # 教学反馈快照
    evidence_state = Column(String(32), nullable=True, comment="证据五态")
    verification_status = Column(String(32), nullable=True, comment="验证状态")
    hint_level = Column(Integer, nullable=True, comment="提示层级 1-3")
    next_action = Column(String(32), nullable=True, comment="下一步动作")

    # 用户反馈（后续点击有帮助/无帮助时更新）
    feedback = Column(String(32), nullable=True, comment="用户反馈 helpful/not_helpful")

    __table_args__ = (
        UniqueConstraint("request_id", name="uq_agent_interaction_request"),
        Index("idx_ai_visitor_lesson", "visitor_id", "lesson_slug"),
        Index("idx_ai_visitor_created", "visitor_id", "created_time"),
    )
