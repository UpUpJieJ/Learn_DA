"""
阶段 1：统一学习事实 - Pydantic Schema

本模块只有读接口，因此只定义响应模型。状态变更走 `/analytics/track`，
请求模型见 ``app.analytics.schemas.EventTrackRequest``。

身份遵循阶段 0 的签名匿名 session 约定：visitor_id 不出现在请求体，统一由
``get_anonymous_visitor_id`` 从 session cookie 注入。
"""

from typing import Optional

from app.utils.base_response import BaseResponseModel


# ── 响应模型 ─────────────────────────────────────────


class LessonProgressDetail(BaseResponseModel):
    """单课进度详情"""

    lesson_slug: str
    status: str  # started / completed / uncompleted
    completed_at: Optional[str] = None
    last_activity_at: Optional[str] = None
    attempt_count: int = 0
    success_count: int = 0
    error_count: int = 0


class LearnerProgressSummary(BaseResponseModel):
    """学习者完整进度投影"""

    completed_lessons: list[str] = []
    last_visited_slug: Optional[str] = None
    lesson_details: list[LessonProgressDetail] = []
    total_completed: int = 0
    total_started: int = 0
