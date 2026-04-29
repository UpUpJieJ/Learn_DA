"""
内容加载器：从 Markdown 文件加载课程和示例
"""

import re
from pathlib import Path
from typing import Any

import yaml


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    解析 Markdown 文件的 frontmatter
    
    格式：
    ---
    key: value
    ---
    
    返回: (frontmatter_dict, markdown_body)
    """
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)
    
    if not match:
        return {}, content
    
    frontmatter_text = match.group(1)
    body = match.group(2)
    
    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        frontmatter = {}
    
    return frontmatter, body.strip()


def extract_code_example(content: str) -> str | None:
    """
    从 Markdown 内容中提取标记为 example 的代码块
    
    格式：
    ```python:example
    code here
    ```
    """
    pattern = r'```python:example\s*\n(.*?)\n```'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    return None


def load_lesson_from_file(file_path: Path) -> dict[str, Any] | None:
    """
    从单个 Markdown 文件加载课程
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        frontmatter, body = parse_frontmatter(content)
        
        if not frontmatter:
            return None
        
        # 提取代码示例
        code_example = extract_code_example(content)
        
        lesson = {
            'id': frontmatter.get('id'),
            'slug': frontmatter.get('slug'),
            'title': frontmatter.get('title'),
            'category': frontmatter.get('category'),
            'difficulty': frontmatter.get('difficulty'),
            'description': frontmatter.get('description', ''),
            'estimated_minutes': frontmatter.get('estimated_minutes', 15),
            'order': frontmatter.get('order', 0),
            'tags': frontmatter.get('tags', []),
            'content': body,
            'code_example': code_example or '',
            'prev_lesson': frontmatter.get('prev_lesson'),
            'next_lesson': frontmatter.get('next_lesson'),
        }
        
        # 验证必需字段
        required_fields = ['id', 'slug', 'title', 'category', 'difficulty']
        for field in required_fields:
            if lesson.get(field) is None:
                print(f"[ContentLoader] Warning: {file_path.name} 缺少必需字段 '{field}'")
                return None
        
        return lesson
        
    except Exception as e:
        print(f"[ContentLoader] Error loading {file_path}: {e}")
        return None


def load_example_from_file(file_path: Path) -> dict[str, Any] | None:
    """
    从单个 Markdown 文件加载示例
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        frontmatter, body = parse_frontmatter(content)
        
        if not frontmatter:
            return None
        
        # 提取代码（第一个 python 代码块）
        code_match = re.search(r'```python\s*\n(.*?)\n```', body, re.DOTALL)
        code = code_match.group(1).strip() if code_match else ''
        
        example = {
            'slug': frontmatter.get('slug'),
            'title': frontmatter.get('title'),
            'topic': frontmatter.get('topic'),
            'summary': frontmatter.get('summary', ''),
            'code': code,
            'expected_output': frontmatter.get('expected_output', ''),
        }
        
        # 验证必需字段
        if not example['slug'] or not example['title']:
            print(f"[ContentLoader] Warning: {file_path.name} 缺少 slug 或 title")
            return None
        
        return example
        
    except Exception as e:
        print(f"[ContentLoader] Error loading {file_path}: {e}")
        return None


def load_all_lessons(content_dir: Path | None = None) -> list[dict[str, Any]]:
    """
    加载所有课程
    """
    if content_dir is None:
        content_dir = Path(__file__).parent.parent.parent / 'content'
    
    lessons_dir = content_dir / 'lessons'
    if not lessons_dir.exists():
        print(f"[ContentLoader] Lessons directory not found: {lessons_dir}")
        return []
    
    lessons = []
    for md_file in sorted(lessons_dir.glob('*.md')):
        lesson = load_lesson_from_file(md_file)
        if lesson:
            lessons.append(lesson)
            print(f"[ContentLoader] Loaded lesson: {lesson['slug']}")
    
    # 按 order 排序
    lessons.sort(key=lambda x: x.get('order', 0))
    
    return lessons


def load_all_examples(content_dir: Path | None = None) -> list[dict[str, Any]]:
    """
    加载所有示例
    """
    if content_dir is None:
        content_dir = Path(__file__).parent.parent.parent / 'content'
    
    examples_dir = content_dir / 'examples'
    if not examples_dir.exists():
        print(f"[ContentLoader] Examples directory not found: {examples_dir}")
        return []
    
    examples = []
    for md_file in sorted(examples_dir.glob('*.md')):
        example = load_example_from_file(md_file)
        if example:
            examples.append(example)
            print(f"[ContentLoader] Loaded example: {example['slug']}")
    
    return examples
