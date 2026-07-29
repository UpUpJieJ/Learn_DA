"""embedding 持久化缓存（阶段 ① Task 1.2）。

按 sha256(model + 文本) 作缓存键：课程内容或模型变化自动 miss，
相同内容跨进程/重启复用，满足"相同课程版本只嵌入一次"。
缓存读写使用独立短事务 session，不依赖请求级 db session，
因为 KnowledgeRetriever 是 lifespan 单例。
"""

import hashlib
import json
from typing import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import AgentEmbedding


def embedding_content_hash(model: str, text: str) -> str:
    payload = f"{model}\x00{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class EmbeddingCache:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession] | None = None,
    ) -> None:
        if session_factory is None:
            from app.core.database.database import AsyncSessionLocal

            session_factory = AsyncSessionLocal
        self._session_factory: async_sessionmaker | Callable[[], AsyncSession] = (
            session_factory
        )

    async def get_many(
        self,
        model: str,
        chunk_hashes: Iterable[str],
    ) -> dict[str, list[float]]:
        hashes = list(chunk_hashes)
        if not hashes:
            return {}
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentEmbedding.chunk_hash, AgentEmbedding.vector_json).where(
                    AgentEmbedding.model == model,
                    AgentEmbedding.chunk_hash.in_(hashes),
                )
            )
            return {
                chunk_hash: json.loads(vector_json)
                for chunk_hash, vector_json in result.all()
            }

    async def set_many(
        self,
        model: str,
        vectors: dict[str, list[float]],
    ) -> None:
        if not vectors:
            return
        async with self._session_factory() as session:
            existing_result = await session.execute(
                select(AgentEmbedding.chunk_hash).where(
                    AgentEmbedding.chunk_hash.in_(list(vectors)),
                )
            )
            existing = {row[0] for row in existing_result.all()}
            for chunk_hash, vector in vectors.items():
                if chunk_hash in existing:
                    continue
                session.add(
                    AgentEmbedding(
                        chunk_hash=chunk_hash,
                        model=model,
                        dimension=len(vector),
                        vector_json=json.dumps(vector),
                    )
                )
            await session.commit()
