"""
阶段 1：统一学习事实 - 数据模型

- LearnerLessonProgress: 每节课的学习状态（upsert 语义，非只追加）
- RecommendationCooldown: 推荐冷却持久化
"""

from sqlalchemy import Column, String, Integer, DateTime, Index, UniqueConstraint

from app.core.database.base import BaseModel


class LearnerLessonProgress(BaseModel):
    """学习者课程进度（每 visitor + lesson 唯一一行）"""

    __tablename__ = "learner_lesson_progress"

    visitor_id = Column(String(64), nullable=False, index=True, comment="访客 ID")
    lesson_slug = Column(String(128), nullable=False, comment="课程 slug")
    status = Column(
        String(20),
        nullable=False,
        default="started",
        comment="状态: started / completed / uncompleted",
    )
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="完成时间")
    last_activity_at = Column(
        DateTime(timezone=True), nullable=True, comment="最近活动时间"
    )
    attempt_count = Column(Integer, default=0, comment="代码尝试次数")
    success_count = Column(Integer, default=0, comment="成功次数")
    error_count = Column(Integer, default=0, comment="失败次数")

    __table_args__ = (
        UniqueConstraint("visitor_id", "lesson_slug", name="uq_visitor_lesson"),
        Index("idx_llp_visitor_status", "visitor_id", "status"),
    )


class RecommendationCooldown(BaseModel):
    """推荐冷却记录（持久化，跨请求/重启有效）"""

    __tablename__ = "recommendation_cooldowns"

    visitor_id = Column(String(64), nullable=False, index=True, comment="访客 ID")
    lesson_slug = Column(String(128), nullable=False, comment="课程 slug")
    cooldown_until = Column(
        DateTime(timezone=True), nullable=False, comment="冷却截止时间"
    )

    __table_args__ = (
        UniqueConstraint("visitor_id", "lesson_slug", name="uq_cd_visitor_lesson"),
    )
