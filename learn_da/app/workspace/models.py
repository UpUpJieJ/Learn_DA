"""学习工作区数据模型（改版 M1）。

四张表对应设计稿 §5：

* ``lesson_sessions`` —— 一次课程会话（visitor + lesson 唯一，可续用）
* ``session_cells``   —— 会话里的单元格与它们当前的真实代码/状态
* ``run_events``      —— 每次执行请求的幂等凭据与结果（visitor + request_id 唯一）
* ``task_attempts``   —— 任务提交记录（教学证据，取代 exercise_attempts 的新链路）

旧的 ``exercise_attempts`` 冻结只读，不再写入。
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database.base import BaseModel


class LessonSession(BaseModel):
    """一个访客在一门课上的工作区会话。"""

    __tablename__ = "lesson_sessions"

    visitor_id = Column(String(64), index=True, nullable=False)
    lesson_slug = Column(String(64), index=True, nullable=False)
    content_version = Column(String(64), nullable=False)
    status = Column(String(16), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "visitor_id", "lesson_slug", name="uq_session_visitor_lesson"
        ),
    )


class SessionCell(BaseModel):
    """会话中的一个单元格（起始格 / 任务格 / 草稿格）。"""

    __tablename__ = "session_cells"

    session_id = Column(
        Integer,
        ForeignKey("lesson_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    cell_id = Column(String(64), nullable=False)
    position = Column(Integer, nullable=False)
    kind = Column(String(16), default="task", nullable=False)
    task_id = Column(String(64), nullable=True)
    language = Column(String(16), default="python", nullable=False)
    code = Column(Text, default="", nullable=False)
    status = Column(String(16), default="stale", nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "cell_id", name="uq_cell_session_cell"),
        Index("ix_cell_session_position", "session_id", "position"),
    )


class RunEvent(BaseModel):
    """一次执行请求（幂等键：visitor_id + request_id）。"""

    __tablename__ = "run_events"

    visitor_id = Column(String(64), index=True, nullable=False)
    session_id = Column(
        Integer,
        ForeignKey("lesson_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    request_id = Column(String(64), nullable=False)
    cell_id = Column(String(64), nullable=False)
    stop_at = Column(String(64), nullable=True)
    verdict = Column(String(24), nullable=False)
    duration_ms = Column(Integer, default=0, nullable=False)
    payload = Column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("visitor_id", "request_id", name="uq_run_visitor_request"),
    )


class TaskAttempt(BaseModel):
    """任务提交记录——新的教学证据来源。"""

    __tablename__ = "task_attempts"

    visitor_id = Column(String(64), index=True, nullable=False)
    session_id = Column(
        Integer,
        ForeignKey("lesson_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    lesson_slug = Column(String(64), index=True, nullable=False)
    task_id = Column(String(64), index=True, nullable=False)
    attempt_no = Column(Integer, default=1, nullable=False)
    status = Column(String(16), nullable=False)  # passed | failed | skipped
    # Runner 判定结论：passed | assertion_failed | execution_failed。
    # status 是教学口径（通过/失败/跳过），verdict 保留了「失败在哪一层」，
    # Agent 证据解析依赖它区分「代码跑不起来」与「代码能跑但断言不符」。
    verdict = Column(String(24), nullable=True)
    code = Column(Text, default="", nullable=False)
    actual = Column(Text, default="", nullable=False)
    assertions = Column(Text, default="[]", nullable=False)
    is_confirmed = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_attempt_session_task", "session_id", "task_id"),
    )


class HintUsage(BaseModel):
    """一次分级提示的发放记录（改版 E2 的 ladder 档）。

    层级由服务端按**真实失败次数**算出来（见 ``app/workspace/hints.py``），
    这张表是「已经给到第几层」的唯一凭据：没有它就退回到按提问次数估算，
    会出现「连问 5 个概念问题直接拿到 L3」这种没卡住却拿到近答案的情况。

    记 ``failures_at_hint`` 是为了事后核对层级是否算对（诊断用），
    不参与计算——计算只依赖「上一次提示之后失败了几次」。
    """

    __tablename__ = "hint_usages"

    visitor_id = Column(String(64), index=True, nullable=False)
    session_id = Column(
        Integer,
        ForeignKey("lesson_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    lesson_slug = Column(String(64), index=True, nullable=False)
    task_id = Column(String(64), index=True, nullable=False)
    # 1..3，发放时的层级
    level = Column(Integer, default=1, nullable=False)
    # 发放时的「距上次提示的失败次数」，仅供事后核对
    failures_at_hint = Column(Integer, default=0, nullable=False)
    # 发出去的提示正文（确定性生成，不含模型输出）
    content = Column(Text, default="", nullable=False)

    __table_args__ = (
        Index("ix_hint_session_task", "session_id", "task_id"),
    )