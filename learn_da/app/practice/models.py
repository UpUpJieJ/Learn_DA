"""
Phase 2: 可验证练习闭环 - 数据模型

ExerciseAttempt: 每次练习提交的持久化尝试记录
- (visitor_id, request_id) 唯一约束保证重放幂等
- 代码和输出长度受限
- 按 visitor + exercise 查询最近 Attempt
"""

from sqlalchemy import Column, String, Integer, Text, DateTime, Index, UniqueConstraint

from app.core.database.base import BaseModel


class ExerciseAttempt(BaseModel):
    """练习尝试记录"""

    __tablename__ = "exercise_attempts"

    # 身份
    visitor_id = Column(String(64), nullable=False, index=True, comment="访客 ID")
    request_id = Column(String(64), nullable=False, comment="前端执行请求 ID（幂等键）")

    # 关联
    lesson_slug = Column(String(128), nullable=False, comment="课程 slug")
    exercise_id = Column(String(128), nullable=False, comment="练习 ID")
    execution_id = Column(
        String(64), nullable=True, comment="Runner 返回的 execution ID"
    )

    # 提交内容
    source = Column(String(32), nullable=False, default="playground", comment="来源")
    language = Column(String(16), nullable=False, default="python", comment="代码语言")
    code = Column(Text, nullable=False, comment="提交的代码")

    # 执行结果
    execution_status = Column(
        String(20),
        nullable=False,
        comment="执行状态: success / error / timeout / rejected / unavailable",
    )
    verification_status = Column(
        String(20),
        nullable=False,
        default="not_run",
        comment="验证状态: not_run / passed / failed / unverifiable",
    )
    failure_reason = Column(
        Text, nullable=True, comment="失败原因（仅 failed/unverifiable）"
    )

    # 输出（受限长度）
    stdout = Column(Text, nullable=True, comment="标准输出")
    stderr = Column(Text, nullable=True, comment="标准错误")
    duration_ms = Column(Integer, nullable=True, comment="执行耗时（毫秒）")

    __table_args__ = (
        UniqueConstraint("visitor_id", "request_id", name="uq_attempt_visitor_request"),
        Index("idx_ea_visitor_exercise", "visitor_id", "exercise_id"),
        Index("idx_ea_visitor_lesson", "visitor_id", "lesson_slug"),
        Index("idx_ea_created_time", "created_time"),
    )
