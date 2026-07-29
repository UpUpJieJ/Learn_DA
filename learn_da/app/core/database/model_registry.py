"""
集中导入所有 SQLAlchemy 模型，供 Alembic 自动发现 metadata 使用。

新增模型后，请在这里补充导入，确保 `alembic revision --autogenerate`
能够感知到表结构变化。
"""

from app.agent.models import AgentEmbedding  # noqa: F401
from app.analytics.models import (  # noqa: F401
    LearningRecord,
    UserProfile,
    DailyStats,
    CodeSnapshot,
)
from app.learner_state.models import (  # noqa: F401
    LearnerLessonProgress,
    RecommendationCooldown,
)

__all__ = [
    "AgentEmbedding",
    "LearningRecord",
    "UserProfile",
    "DailyStats",
    "CodeSnapshot",
    "LearnerLessonProgress",
    "RecommendationCooldown",
]
