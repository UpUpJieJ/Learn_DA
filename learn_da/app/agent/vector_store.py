import abc
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from app.agent.knowledge import KnowledgeChunk
from config.settings import settings


@dataclass
class VectorSearchResult:
    chunk: KnowledgeChunk
    score: float


class VectorStore(abc.ABC):
    @abc.abstractmethod
    async def add_chunks(self, chunks: List[KnowledgeChunk]) -> None:
        pass

    @abc.abstractmethod
    async def search(
        self,
        query: str,
        current_lesson: Optional[str] = None,
        limit: int = 3,
    ) -> List[VectorSearchResult]:
        pass

    @abc.abstractmethod
    async def clear(self) -> None:
        pass


class InMemoryVectorStore(VectorStore):
    def __init__(self):
        self._chunks: List[KnowledgeChunk] = []

    async def add_chunks(self, chunks: List[KnowledgeChunk]) -> None:
        self._chunks.extend(chunks)

    async def search(
        self,
        query: str,
        current_lesson: Optional[str] = None,
        limit: int = 3,
    ) -> List[VectorSearchResult]:
        query_terms = set(self._tokenize(query.lower()))
        results = []

        for chunk in self._chunks:
            chunk_text = self._chunk_text_for_search(chunk).lower()
            chunk_terms = set(self._tokenize(chunk_text))
            if not query_terms:
                score = 0.0
            else:
                score = len(query_terms & chunk_terms) / len(query_terms)

            if current_lesson and chunk.lesson_slug == current_lesson:
                score += 0.2

            if score > 0:
                results.append(VectorSearchResult(chunk=chunk, score=score))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    async def clear(self) -> None:
        self._chunks = []

    def _tokenize(self, text: str) -> List[str]:
        import re

        terms = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|[\u4e00-\u9fa5]+", text)
        return [term for term in terms if len(term) > 1]

    def _chunk_text_for_search(self, chunk: KnowledgeChunk) -> str:
        return "\n".join(
            [
                f"课程：{chunk.lesson_title}",
                f"分类：{chunk.category}",
                f"小节：{chunk.heading}",
                chunk.text,
            ]
        )


class JSONFileVectorStore(VectorStore):
    def __init__(self, file_path: str = "knowledge_store.json"):
        self._file_path = Path(file_path)
        self._chunks: List[KnowledgeChunk] = []
        self._load_from_file()

    def _load_from_file(self):
        if self._file_path.exists():
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._chunks = [
                        KnowledgeChunk(
                            lesson_slug=item["lesson_slug"],
                            lesson_title=item["lesson_title"],
                            category=item["category"],
                            heading=item["heading"],
                            text=item["text"],
                        )
                        for item in data
                    ]
            except Exception:
                self._chunks = []

    def _save_to_file(self):
        data = [
            {
                "lesson_slug": chunk.lesson_slug,
                "lesson_title": chunk.lesson_title,
                "category": chunk.category,
                "heading": chunk.heading,
                "text": chunk.text,
            }
            for chunk in self._chunks
        ]
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def add_chunks(self, chunks: List[KnowledgeChunk]) -> None:
        self._chunks.extend(chunks)
        self._save_to_file()

    async def search(
        self,
        query: str,
        current_lesson: Optional[str] = None,
        limit: int = 3,
    ) -> List[VectorSearchResult]:
        query_terms = set(self._tokenize(query.lower()))
        results = []

        for chunk in self._chunks:
            chunk_text = self._chunk_text_for_search(chunk).lower()
            chunk_terms = set(self._tokenize(chunk_text))
            if not query_terms:
                score = 0.0
            else:
                score = len(query_terms & chunk_terms) / len(query_terms)

            if current_lesson and chunk.lesson_slug == current_lesson:
                score += 0.2

            if score > 0:
                results.append(VectorSearchResult(chunk=chunk, score=score))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    async def clear(self) -> None:
        self._chunks = []
        if self._file_path.exists():
            self._file_path.unlink()

    def _tokenize(self, text: str) -> List[str]:
        import re

        terms = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|[\u4e00-\u9fa5]+", text)
        return [term for term in terms if len(term) > 1]

    def _chunk_text_for_search(self, chunk: KnowledgeChunk) -> str:
        return "\n".join(
            [
                f"课程：{chunk.lesson_title}",
                f"分类：{chunk.category}",
                f"小节：{chunk.heading}",
                chunk.text,
            ]
        )


def get_vector_store() -> VectorStore:
    store_type = getattr(settings, "VECTOR_STORE_TYPE", "in_memory")
    if store_type == "json_file":
        file_path = getattr(settings, "VECTOR_STORE_PATH", "knowledge_store.json")
        return JSONFileVectorStore(file_path)
    return InMemoryVectorStore()
