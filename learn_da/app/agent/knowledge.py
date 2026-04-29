import math
import re
from dataclasses import dataclass
from typing import Sequence

from openai import AsyncOpenAI

from app.core.content_loader import load_all_lessons
from config.settings import settings


@dataclass(frozen=True)
class EmbeddingConfig:
    api_key: str | None
    base_url: str | None
    model: str | None
    provider: str = "openai_compatible"
    dimension: int | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    @classmethod
    def from_settings(cls) -> "EmbeddingConfig":
        return cls(
            api_key=settings.LEARN_DA_EMBEDDING_API_KEY,
            base_url=settings.LEARN_DA_EMBEDDING_BASE_URL,
            model=settings.LEARN_DA_EMBEDDING_MODEL,
            provider=settings.LEARN_DA_EMBEDDING_PROVIDER,
            dimension=settings.LEARN_DA_EMBEDDING_DIM,
        )


@dataclass(frozen=True)
class KnowledgeChunk:
    lesson_slug: str
    lesson_title: str
    category: str
    heading: str
    text: str
    score: float = 0.0


class OpenAICompatibleEmbeddingClient:
    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=self.config.model,
            input=list(texts),
        )
        items = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in items]


class KnowledgeRetriever:
    def __init__(
        self,
        lessons: list[dict] | None = None,
        embedding_config: EmbeddingConfig | None = None,
        embedding_client: OpenAICompatibleEmbeddingClient | None = None,
    ) -> None:
        self.lessons = lessons if lessons is not None else load_all_lessons()
        self.chunks = self._build_chunks(self.lessons)
        self.embedding_config = embedding_config or EmbeddingConfig.from_settings()
        self.embedding_client = embedding_client
        if self.embedding_client is None and self.embedding_config.enabled:
            self.embedding_client = OpenAICompatibleEmbeddingClient(self.embedding_config)
        self._chunk_embeddings: list[list[float]] | None = None

    async def search(
        self,
        query: str,
        current_lesson: str | None = None,
        limit: int = 3,
    ) -> list[KnowledgeChunk]:
        if not query.strip() or not self.chunks:
            return []

        if self.embedding_client is not None and self.embedding_config.enabled:
            try:
                return await self._embedding_search(query, current_lesson, limit)
            except Exception:
                pass

        return self._keyword_search(query, current_lesson, limit)

    async def _embedding_search(
        self,
        query: str,
        current_lesson: str | None,
        limit: int,
    ) -> list[KnowledgeChunk]:
        assert self.embedding_client is not None
        texts = [self._chunk_text_for_embedding(chunk) for chunk in self.chunks]
        if self._chunk_embeddings is None:
            self._chunk_embeddings = await self.embedding_client.embed_texts(texts)
        query_embedding = (await self.embedding_client.embed_texts([query]))[0]

        ranked = []
        for chunk, embedding in zip(self.chunks, self._chunk_embeddings):
            score = self._cosine_similarity(query_embedding, embedding)
            if current_lesson and chunk.lesson_slug == current_lesson:
                score += 0.08
            ranked.append(self._with_score(chunk, score))
        return sorted(ranked, key=lambda chunk: chunk.score, reverse=True)[:limit]

    def _keyword_search(
        self,
        query: str,
        current_lesson: str | None,
        limit: int,
    ) -> list[KnowledgeChunk]:
        query_terms = self._tokenize(query)
        ranked = []
        for chunk in self.chunks:
            text = self._chunk_text_for_embedding(chunk).lower()
            score = 0.0
            for term in query_terms:
                if term in text:
                    score += 1.0
            if current_lesson and chunk.lesson_slug == current_lesson:
                score += 0.5
            if score > 0:
                ranked.append(self._with_score(chunk, score))
        return sorted(ranked, key=lambda chunk: chunk.score, reverse=True)[:limit]

    def _build_chunks(self, lessons: list[dict]) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for lesson in lessons:
            for heading, text in self._split_markdown(lesson.get("content", "")):
                chunks.append(
                    KnowledgeChunk(
                        lesson_slug=lesson.get("slug", ""),
                        lesson_title=lesson.get("title", ""),
                        category=lesson.get("category", ""),
                        heading=heading,
                        text=text,
                    )
                )
            code_example = lesson.get("code_example")
            if code_example:
                chunks.append(
                    KnowledgeChunk(
                        lesson_slug=lesson.get("slug", ""),
                        lesson_title=lesson.get("title", ""),
                        category=lesson.get("category", ""),
                        heading="示例代码",
                        text=code_example,
                    )
                )
        return [chunk for chunk in chunks if chunk.text.strip()]

    def _split_markdown(self, content: str) -> list[tuple[str, str]]:
        sections: list[tuple[str, str]] = []
        current_heading = "课程概览"
        current_lines: list[str] = []

        for line in content.splitlines():
            heading_match = re.match(r"^(#{2,6})\s+(.+)$", line)
            if heading_match:
                if current_lines:
                    sections.append((current_heading, "\n".join(current_lines).strip()))
                current_heading = heading_match.group(2).strip()
                current_lines = []
                continue
            current_lines.append(line)

        if current_lines:
            sections.append((current_heading, "\n".join(current_lines).strip()))
        return sections or [("课程概览", content.strip())]

    def _tokenize(self, text: str) -> list[str]:
        terms = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|[\u4e00-\u9fff]+", text.lower())
        return [term for term in terms if len(term) > 1]

    def _chunk_text_for_embedding(self, chunk: KnowledgeChunk) -> str:
        return "\n".join(
            [
                f"课程：{chunk.lesson_title}",
                f"分类：{chunk.category}",
                f"小节：{chunk.heading}",
                chunk.text,
            ]
        )

    def _with_score(self, chunk: KnowledgeChunk, score: float) -> KnowledgeChunk:
        return KnowledgeChunk(
            lesson_slug=chunk.lesson_slug,
            lesson_title=chunk.lesson_title,
            category=chunk.category,
            heading=chunk.heading,
            text=chunk.text,
            score=score,
        )

    def _cosine_similarity(self, left: Sequence[float], right: Sequence[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)


def build_knowledge_block(chunks: list[KnowledgeChunk]) -> str:
    if not chunks:
        return ""

    parts = ["相关知识点："]
    for index, chunk in enumerate(chunks, start=1):
        text = chunk.text.strip()
        if len(text) > 900:
            text = f"{text[:900]}..."
        parts.append(
            "\n".join(
                [
                    f"{index}. {chunk.lesson_title} / {chunk.heading}",
                    f"来源：{chunk.lesson_slug}，分类：{chunk.category}",
                    f"内容：{text}",
                ]
            )
        )
    return "\n\n".join(parts)
