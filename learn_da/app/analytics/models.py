"""
Phase 1: 学习行为追踪数据表
- learning_records: 学习行为记录（代码保存、运行、完成课程等）
- user_profiles: 用户画像（累计学习时长、连续天数、能力雷达图等）
- daily_stats: 每日全局统计（平台级 DAU / 代码运行次数等）
- code_snapshots: 代码快照（用于回看历史代码）
"""

from sqlalchemy import Column, String, Integer, Float, Text, Index

from app.core.database.base import BaseModel


class LearningRecord(BaseModel):
    """学习行为记录"""
    __tablename__ = "learning_records"

    visitor_id = Column(String(64), nullable=False, index=True, comment="访客 ID（前端生成）")
    event_type = Column(String(32), nullable=False, comment="事件类型: code_run / code_save / lesson_complete / ai_help / lesson_start")
    lesson_slug = Column(String(128), nullable=True, comment="关联课程 slug，全局事件可为空")
    duration_seconds = Column(Integer, nullable=True, comment="持续时长（秒），如课程阅读时长")

    __table_args__ = (
        Index("idx_lr_visitor_event", "visitor_id", "event_type"),
        Index("idx_lr_lesson_slug", "lesson_slug"),
        Index("idx_lr_created_time", "created_time"),
    )


class UserProfile(BaseModel):
    """用户画像"""
    __tablename__ = "user_profiles"

    visitor_id = Column(String(64), nullable=False, unique=True, index=True, comment="访客 ID")
    total_learning_minutes = Column(Integer, default=0, comment="累计学习时长（分钟）")
    lessons_completed = Column(Integer, default=0, comment="已完成课程数")
    code_runs = Column(Integer, default=0, comment="代码运行次数")
    ai_helps = Column(Integer, default=0, comment="AI 助手使用次数")
    current_streak = Column(Integer, default=0, comment="当前连续学习天数")
    longest_streak = Column(Integer, default=0, comment="最长连续学习天数")
    last_active_date = Column(String(10), nullable=True, comment="最后活跃日期 YYYY-MM-DD")
    polars_score = Column(Float, default=0.0, comment="Polars 能力分 (0-100)")
    duckdb_score = Column(Float, default=0.0, comment="DuckDB 能力分 (0-100)")
    sql_score = Column(Float, default=0.0, comment="SQL 能力分 (0-100)")
    data_processing_score = Column(Float, default=0.0, comment="数据处理能力分 (0-100)")
    api_mastery_score = Column(Float, default=0.0, comment="API 熟练度分 (0-100)")


class DailyStats(BaseModel):
    """每日全局统计"""
    __tablename__ = "daily_stats"

    stat_date = Column(String(10), nullable=False, unique=True, index=True, comment="日期 YYYY-MM-DD")
    active_users = Column(Integer, default=0, comment="当日活跃用户数")
    new_users = Column(Integer, default=0, comment="当日新增用户数")
    code_runs = Column(Integer, default=0, comment="代码运行次数")
    lessons_completed = Column(Integer, default=0, comment="课程完成次数")
    ai_helps = Column(Integer, default=0, comment="AI 助手使用次数")
    avg_session_minutes = Column(Float, default=0.0, comment="平均学习时长（分钟）")


class CodeSnapshot(BaseModel):
    """代码快照"""
    __tablename__ = "code_snapshots"

    visitor_id = Column(String(64), nullable=False, index=True, comment="访客 ID")
    lesson_slug = Column(String(128), nullable=True, comment="关联课程 slug")
    code = Column(Text, nullable=False, comment="代码内容")
    language = Column(String(16), default="python", comment="代码语言")
    version = Column(Integer, default=1, comment="版本号")
    description = Column(String(256), nullable=True, comment="快照描述")

    __table_args__ = (
        Index("idx_cs_visitor_lesson", "visitor_id", "lesson_slug"),
    )
