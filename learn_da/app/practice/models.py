"""
Phase 2 遗留表：``exercise_attempts``（改版 M4 起冻结只读）

练习链路已于 2026-10-24 下线，工作区的任务提交写入 ``task_attempts``。
本表保留只为：

- 迁移历史完整（``2e532d3dd383_phase2_exercise_attempts`` 已建表，删表需要新迁移）；
- 老数据留存，便于追溯改版前的历史记录。

**不要再往这张表写入新数据**：``app.practice`` 里已没有 repository / service，
``model_registry`` 仍登记它以便 Alembic 不把表当成孤儿。
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
