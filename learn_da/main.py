from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from starlette.middleware.sessions import SessionMiddleware

from app.core import get_db, setup_exception_handlers
from app.middleware import setup_access_log_middleware, setup_cors_middleware
from app.middleware.security import setup_security_middleware
from app.sandbox import RunnerClient
from app.utils import auto_register_routers, log
from app.utils.base_response import StdResp
from app.utils.limiter import setup_limiter_middleware
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(f"{settings.APP_NAME} 启动中")

    # 阶段 4：内容索引在启动时 lint 并构建一次；内容错误直接阻断启动
    # （fail closed），避免运行时缺课或断链。
    from app.core.content_catalog import preload_content_index

    app.state.content_index = preload_content_index()

    # Runner client — lives for the entire application lifetime.
    http_client = httpx.AsyncClient()
    app.state.runner_client = RunnerClient(http_client)

    # Phase 2: 暴露 AsyncSession factory，供 playground 练习执行在同一事务中
    # 写 Attempt + code_run + Learner State
    from app.core.database.database import AsyncSessionLocal
    app.state.db_session_factory = AsyncSessionLocal

    # Agent 知识检索器 — 课程 Markdown 只在启动时加载一次，全部请求共享；
    # embedding 向量经 EmbeddingCache 按内容哈希持久化，重启后不重复嵌入。
    # LLM client 同为进程级单例：连接池全请求复用，shutdown 时统一关闭。
    app.state.agent_llm_client = None
    if "agent" in settings.enabled_app_modules:
        from app.agent.embedding_cache import EmbeddingCache
        from app.agent.knowledge import KnowledgeRetriever

        app.state.knowledge_retriever = KnowledgeRetriever(
            embedding_cache=EmbeddingCache()
        )

        if settings.effective_llm_api_key:
            from openai import AsyncOpenAI

            app.state.agent_llm_client = AsyncOpenAI(
                api_key=settings.effective_llm_api_key,
                base_url=settings.effective_llm_base_url,
            )

    yield

    await app.state.runner_client.close()

    if app.state.agent_llm_client is not None:
        await app.state.agent_llm_client.close()

    from app.core.database.database import engine

    await engine.dispose()
    log.info(f"{settings.APP_NAME} 已关闭")


_is_prod = settings.APP_ENV == "production"
_docs_url = "/docs" if not _is_prod or settings.OPENAPI_ENABLED else None
_openapi_url = "/openapi.json" if not _is_prod or settings.OPENAPI_ENABLED else None

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
    docs_url=_docs_url,
    openapi_url=_openapi_url,
    redoc_url=None,
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Polars + DuckDB 交互式学习平台后端 API",
        routes=app.routes,
    )

    app.openapi_schema = openapi_schema
    return openapi_schema


setattr(app, "openapi", custom_openapi)

setup_exception_handlers(app)
setup_cors_middleware(app)
setup_security_middleware(app)
setup_access_log_middleware(app)

# Signed anonymous session (HttpOnly cookie)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    session_cookie=settings.SESSION_COOKIE_NAME,
    https_only=settings.APP_ENV == "production",
    same_site="lax",
    max_age=31_536_000,  # 1 year
)

if settings.RATE_LIMIT_ENABLED:
    setup_limiter_middleware(app)

main_router = APIRouter(prefix=settings.API_PREFIX)
v1_router = APIRouter(prefix=f"/{settings.API_VERSION}")
auto_register_routers(app=app, main_router=v1_router)
main_router.include_router(v1_router)
app.include_router(main_router)


@app.get("/")
async def read_root():
    return StdResp.success(
        data={
            "name": settings.APP_NAME,
            "env": settings.APP_ENV,
            "apiPrefix": f"{settings.API_PREFIX}/{settings.API_VERSION}",
            "enabledModules": settings.enabled_app_modules,
        },
        msg="Learn DA backend is ready",
    )


@app.get("/live")
async def liveness():
    """Process liveness — does not check external dependencies."""
    return StdResp.success(data={"status": "ok"})


@app.get("/ready")
async def readiness(
    db: AsyncSession = Depends(get_db),
):
    """Readiness — checks database and Runner."""
    checks: dict[str, str] = {}

    # Database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as exc:
        checks["database"] = f"unhealthy: {exc}"

    # Runner
    runner_client: RunnerClient | None = getattr(
        app.state, "runner_client", None)
    if runner_client and await runner_client.is_ready():
        checks["runner"] = "healthy"
    else:
        checks["runner"] = "unhealthy"

    all_ok = all(v == "healthy" or v == "disabled" for v in checks.values())

    if not all_ok:
        return StdResp.error(
            msg="Readiness check failed",
            code=503,
            data=checks,
        ).to_response()

    return StdResp.success(data=checks, msg="All services ready")


# Deprecated: kept for deployment compatibility; delegates to readiness.
@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Deprecated — use /live and /ready instead."""
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    response_data = {
        "app": "healthy",
        "database": db_status,
    }

    if "unhealthy" in db_status:
        return StdResp.error(
            msg="Health check failed",
            code=503,
            data=response_data,
        ).to_response()

    return StdResp.success(
        data=response_data,
        msg="All services are healthy",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_ENV == "development",
    )
