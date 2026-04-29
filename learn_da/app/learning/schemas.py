from app.utils.base_response import BaseResponseModel


class LessonNav(BaseResponseModel):
    slug: str
    title: str


class LessonSummary(BaseResponseModel):
    id: int
    slug: str
    title: str
    description: str
    category: str
    difficulty: str
    estimated_minutes: int = 15  # → estimatedMinutes in JSON
    order: int = 0
    tags: list[str] = []


class LessonDetail(LessonSummary):
    content: str  # markdown body
    code_example: str  # → codeExample in JSON
    prev_lesson: LessonNav | None = None  # → prevLesson in JSON
    next_lesson: LessonNav | None = None  # → nextLesson in JSON


class ExampleSummary(BaseResponseModel):
    slug: str
    title: str
    topic: str
    summary: str


class ExampleDetail(ExampleSummary):
    code: str
    expected_output: str  # → expectedOutput in JSON
