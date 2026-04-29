from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db, setup_exception_handlers
from app.middleware import setup_access_log_middleware, setup_cors_middleware
from app.middleware.security import setup_security_middleware
from app.utils import auto_register_routers, log
from app.utils.base_response import StdResp
from app.utils.limiter import setup_limiter_middleware
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(f"{settings.APP_NAME} 启动中")
    try:
        if settings.REDIS_ENABLED:
            from app.core.redis import AsyncRedisClient

            redis_async = AsyncRedisClient()
            await redis_async.ping()
            log.info("Redis 连接检查成功")
    except Exception as exc:
        log.error(f"应用启动初始化失败: {exc}")

    yield

    if settings.REDIS_ENABLED:
        from app.core.redis import redis_pool_manager

        redis_pool_manager.close_all_pools()
    log.info(f"{settings.APP_NAME} 已关闭")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)


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
    return app.openapi_schema


setattr(app, "openapi", custom_openapi)

setup_exception_handlers(app)
setup_cors_middleware(app)
setup_security_middleware(app)
setup_access_log_middleware(app)
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


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    redis_status = "disabled"
    if settings.REDIS_ENABLED:
        try:
            from app.core.redis import AsyncRedisClient

            redis_client = AsyncRedisClient()
            await redis_client.ping()
            redis_status = "healthy"
        except Exception as exc:
            redis_status = f"unhealthy: {exc}"

    response_data = {
        "app": "healthy",
        "database": db_status,
        "redis": redis_status,
    }

    if "unhealthy" in db_status or "unhealthy" in redis_status:
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
