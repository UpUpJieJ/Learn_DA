from typing import Any

from app.core.content_loader import load_all_lessons, load_all_examples
from .schemas import ExampleDetail, LessonDetail, LessonNav


class LearningRepository:
    """
    学习资源仓库 - 从 Markdown 文件加载课程和示例
    """
    
    def __init__(self):
        self._lessons: list[LessonDetail] | None = None
        self._examples: list[ExampleDetail] | None = None
    
    def _load_lessons(self) -> list[LessonDetail]:
        """懒加载课程数据"""
        if self._lessons is None:
            raw_lessons = load_all_lessons()
            self._lessons = []
            
            # 构建 slug -> lesson 映射，用于查找前后课程
            slug_map = {l['slug']: l for l in raw_lessons}
            
            for raw in raw_lessons:
                # 处理 prev_lesson
                prev_lesson = None
                if raw.get('prev_lesson'):
                    prev = raw['prev_lesson']
                    prev_lesson = LessonNav(slug=prev['slug'], title=prev['title'])
                
                # 处理 next_lesson
                next_lesson = None
                if raw.get('next_lesson'):
                    next_l = raw['next_lesson']
                    next_lesson = LessonNav(slug=next_l['slug'], title=next_l['title'])
                
                lesson = LessonDetail(
                    id=raw['id'],
                    slug=raw['slug'],
                    title=raw['title'],
                    category=raw['category'],
                    difficulty=raw['difficulty'],
                    description=raw.get('description', ''),
                    estimated_minutes=raw.get('estimated_minutes', 15),
                    order=raw.get('order', 0),
                    tags=raw.get('tags', []),
                    content=raw['content'],
                    code_example=raw.get('code_example', ''),
                    prev_lesson=prev_lesson,
                    next_lesson=next_lesson,
                )
                self._lessons.append(lesson)
        
        return self._lessons
    
    def _load_examples(self) -> list[ExampleDetail]:
        """懒加载示例数据"""
        if self._examples is None:
            raw_examples = load_all_examples()
            self._examples = [
                ExampleDetail(
                    slug=raw['slug'],
                    title=raw['title'],
                    topic=raw['topic'],
                    summary=raw.get('summary', ''),
                    code=raw.get('code', ''),
                    expected_output=raw.get('expected_output', ''),
                )
                for raw in raw_examples
            ]
        
        return self._examples
    
    def list_lessons(self) -> list[LessonDetail]:
        """获取所有课程列表"""
        return self._load_lessons()

    def get_lesson(self, slug: str) -> LessonDetail | None:
        """根据 slug 获取课程详情"""
        lessons = self._load_lessons()
        return next(
            (lesson for lesson in lessons if lesson.slug == slug),
            None,
        )

    def list_examples(self) -> list[ExampleDetail]:
        """获取所有示例列表"""
        return self._load_examples()

    def get_example(self, slug: str) -> ExampleDetail | None:
        """根据 slug 获取示例详情"""
        examples = self._load_examples()
        return next(
            (example for example in examples if example.slug == slug),
            None,
        )

    def get_category_stats(self) -> list[dict[str, Any]]:
        """获取分类统计"""
        from collections import Counter
        lessons = self._load_lessons()
        counts = Counter(lesson.category for lesson in lessons)
        label_map = {"polars": "🐻‍❄️ Polars", "duckdb": "🦆 DuckDB", "combined": "⚡ 组合实战"}
        return [
            {"category": cat, "label": label_map.get(cat, cat), "count": count}
            for cat, count in counts.items()
        ]
    
    def reload(self):
        """重新加载内容（用于开发时热重载）"""
        self._lessons = None
        self._examples = None
