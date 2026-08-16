from __future__ import annotations

from app.utils.base_response import BaseResponseModel


class LessonNav(BaseResponseModel):
    slug: str
    title: str


class LessonSummary(BaseResponseModel):
    id: int
    slug: str
    title: str
    description: str
    topic: str = "data-analysis"
    category: str
    difficulty: str
    estimated_minutes: int = 15  # → estimatedMinutes in JSON
    order: int = 0
    tags: list[str] = []
    track: str = ""


class LessonDetail(LessonSummary):
    content: str  # markdown body
    code_example: str  # → codeExample in JSON
    prev_lesson: LessonNav | None = None  # → prevLesson in JSON
    next_lesson: LessonNav | None = None  # → nextLesson in JSON
    # Phase 2: 练习结构（可选，无则降级为纯内容展示）
    practice_objective: str = ""  # → practiceObjective in JSON
    completion_criteria: list[str] = []  # → completionCriteria in JSON
    prerequisites: list[str] = []
    recommended_next: list[str] = []  # → recommendedNext in JSON
    skill_tags: list[str] = []  # → skillTags in JSON
    is_review_friendly: bool = False  # → isReviewFriendly in JSON
    is_branch_point: bool = False  # → isBranchPoint in JSON
    # Phase 2: 正式练习定义（可选，有则优先于 practice_objective）
    exercise: "ExerciseDefinition | None" = None
    # 关联示例摘要（来自 frontmatter examples 引用）
    examples: "list[ExampleSummary]" = []


class ExampleSummary(BaseResponseModel):
    slug: str
    title: str
    topic: str
    summary: str


class ExampleDetail(ExampleSummary):
    code: str


# =====================================================
# Phase 2: 可验证练习定义
# =====================================================


class ExerciseDefinition(BaseResponseModel):
    """课程练习定义（来自 frontmatter exercise 字段）"""

    id: str
    title: str
    language: str = "python"
    starter_code: str = ""
    objective: str = ""
    hints: list[str] = []
    validator: "ExerciseValidator"


class ExerciseValidator(BaseResponseModel):
    """判定器定义（声明式、确定性）"""

    type: str  # stdout_exact / stdout_contains / dataframe_rows
    expected: str | list[str] | dict | None = None


# =====================================================
# Phase 3: 学习建议相关
# =====================================================


class LearningRecommendation(BaseResponseModel):
    """下一步学习建议"""

    type: str  # next_lesson / review_lesson / branch_path / resume_session
    target_slug: str  # → targetSlug in JSON
    target_title: str  # → targetTitle in JSON
    reason: str
    reason_code: str  # → reasonCode in JSON
    priority: int = 1
    action_label: str = "开始学习"  # → actionLabel in JSON
    context: dict | None = None


class RecommendationResponse(BaseResponseModel):
    """建议响应"""

    primary: LearningRecommendation | None
    alternatives: list[LearningRecommendation] = []
