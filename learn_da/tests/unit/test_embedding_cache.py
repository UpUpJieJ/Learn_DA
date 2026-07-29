"""Task 1.2: embedding 按内容哈希持久化，内容不变时不重复嵌入。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.embedding_cache import EmbeddingCache, embedding_content_hash
from app.agent.knowledge import EmbeddingConfig, KnowledgeRetriever

EMBED_CONFIG = EmbeddingConfig(
    api_key="test-key",
    base_url="https://embedding.example.test",
    model="embed-v1",
)


class CountingEmbeddingClient:
    """记录每次 embed_texts 调用，返回确定性向量。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts):
        self.calls.append(list(texts))
        return [[float(len(text) % 7 + 1), 1.0, 0.5] for text in texts]

    @property
    def embedded_texts(self) -> list[str]:
        return [text for call in self.calls for text in call]


def make_lessons(second_content: str = "## 分组聚合\nGROUP BY 用于按类别统计。"):
    return [
        {
            "slug": "polars-lazy",
            "title": "Polars LazyFrame",
            "category": "polars",
            "content": "## Lazy 执行\nLazyFrame 需要 collect() 才会真正执行。",
        },
        {
            "slug": "duckdb-sql",
            "title": "DuckDB SQL",
            "category": "duckdb",
            "content": second_content,
        },
    ]


@pytest.fixture
def session_factory(test_engine):
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.mark.unit
async def test_embedding_cache_roundtrip(session_factory):
    cache = EmbeddingCache(session_factory=session_factory)
    key = embedding_content_hash("roundtrip-model", "some chunk text")

    assert await cache.get_many("roundtrip-model", [key]) == {}

    await cache.set_many("roundtrip-model", {key: [0.1, 0.2, 0.3]})
    loaded = await cache.get_many("roundtrip-model", [key])
    assert loaded == {key: [0.1, 0.2, 0.3]}

    # 重复写入同一哈希不报错、不重复
    await cache.set_many("roundtrip-model", {key: [0.1, 0.2, 0.3]})
    assert await cache.get_many("roundtrip-model", [key]) == {
        key: [0.1, 0.2, 0.3]
    }


@pytest.mark.unit
async def test_unchanged_content_is_not_reembedded_across_instances(
    session_factory,
):
    """模拟应用重启：新 retriever 实例 + 同一持久缓存，chunk 不得重嵌。"""
    cache = EmbeddingCache(session_factory=session_factory)

    first_client = CountingEmbeddingClient()
    first = KnowledgeRetriever(
        lessons=make_lessons(),
        embedding_config=EMBED_CONFIG,
        embedding_client=first_client,
        embedding_cache=cache,
    )
    await first.search("LazyFrame 为什么需要 collect", limit=1)
    chunk_count = len(first.chunks)
    # 首轮：全部 chunk + 1 次 query
    assert len(first_client.embedded_texts) == chunk_count + 1

    second_client = CountingEmbeddingClient()
    second = KnowledgeRetriever(
        lessons=make_lessons(),
        embedding_config=EMBED_CONFIG,
        embedding_client=second_client,
        embedding_cache=cache,
    )
    results = await second.search("LazyFrame 为什么需要 collect", limit=1)

    # 重启后：只嵌 query，chunk 全部命中缓存
    assert len(second_client.embedded_texts) == 1
    assert results and results[0].lesson_slug == "polars-lazy"


@pytest.mark.unit
async def test_changed_chunk_is_the_only_one_reembedded(session_factory):
    cache = EmbeddingCache(session_factory=session_factory)

    warm_client = CountingEmbeddingClient()
    warm = KnowledgeRetriever(
        lessons=make_lessons(),
        embedding_config=EMBED_CONFIG,
        embedding_client=warm_client,
        embedding_cache=cache,
    )
    await warm.search("预热缓存", limit=1)

    changed_content = "## 分组聚合\nGROUP BY 现在支持 GROUPING SETS 示例。"
    changed_client = CountingEmbeddingClient()
    changed = KnowledgeRetriever(
        lessons=make_lessons(second_content=changed_content),
        embedding_config=EMBED_CONFIG,
        embedding_client=changed_client,
        embedding_cache=cache,
    )
    await changed.search("分组聚合怎么写", limit=1)

    # 只有变更的 chunk 被重嵌（外加 1 次 query）
    reembedded_chunks = [
        text for text in changed_client.embedded_texts if "GROUPING SETS" in text
    ]
    assert len(reembedded_chunks) == 1
    assert len(changed_client.embedded_texts) == 2
