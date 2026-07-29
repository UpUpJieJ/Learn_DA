"""
测试全局配置
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database.base import Base
import app.core.database.model_registry as model_registry

MODEL_REGISTRY = model_registry


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def offline_llm_guard(monkeypatch):
    """测试全局离线护栏：清空 .env 中的 LLM/embedding 真实 key。

    FC 默认开启后，若不清空 key，API 测试会真实调用外部 LLM（慢、计费、
    非确定）。需要 key 的测试在自身内部用 monkeypatch 显式设置即可覆盖。
    """
    from config.settings import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "LEARN_DA_EMBEDDING_API_KEY", None)
    monkeypatch.setattr(settings, "LEARN_DA_EMBEDDING_BASE_URL", None)
    monkeypatch.setattr(settings, "LEARN_DA_EMBEDDING_MODEL", None)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine):
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest.fixture(scope="function")
async def client(db_session):
    from main import app
    from app.core.database.database import get_db
    from unittest.mock import AsyncMock
    from app.sandbox.client import RunnerClient

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Inject a mock RunnerClient so tests don't need a real Runner.
    mock_client = AsyncMock(spec=RunnerClient)
    mock_client.is_ready = AsyncMock(return_value=True)
    app.state.runner_client = mock_client

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
