"""Task 1.1/1.3: KnowledgeRetriever 与 LLM client 必须在应用生命周期内共享。"""

from types import SimpleNamespace

import pytest

from app.agent.knowledge import KnowledgeRetriever
from app.agent.service import AgentService
from config.settings import settings


@pytest.fixture
def no_llm(monkeypatch):
    """屏蔽外部 LLM/embedding 调用，保证测试离线。"""
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "FALLBACK_LLM_API_KEY", None)
    monkeypatch.setattr(settings, "LEARN_DA_EMBEDDING_API_KEY", None)
    monkeypatch.setattr(settings, "LEARN_DA_EMBEDDING_BASE_URL", None)
    monkeypatch.setattr(settings, "LEARN_DA_EMBEDDING_MODEL", None)


@pytest.mark.unit
async def test_chat_requests_share_one_knowledge_retriever(
    client, monkeypatch, no_llm
):
    from main import app

    # 清掉可能残留的共享实例，从零观察构建次数
    if hasattr(app.state, "knowledge_retriever"):
        delattr(app.state, "knowledge_retriever")

    init_calls = 0
    original_init = KnowledgeRetriever.__init__

    def counting_init(self, *args, **kwargs):
        nonlocal init_calls
        init_calls += 1
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(KnowledgeRetriever, "__init__", counting_init)

    for _ in range(2):
        resp = await client.post(
            "/api/v1/agent/chat",
            json={"message": "解释一下 Polars 的表达式"},
        )
        assert resp.status_code == 200

    # 两次请求最多构建一次 retriever（课程 Markdown 只加载一次）
    assert init_calls <= 1

    shared = app.state.knowledge_retriever
    resp = await client.post(
        "/api/v1/agent/chat",
        json={"message": "再解释一次"},
    )
    assert resp.status_code == 200
    assert app.state.knowledge_retriever is shared

