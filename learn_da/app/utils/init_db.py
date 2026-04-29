# init_db.py
import asyncio
from contextlib import asynccontextmanager
from app.core import engine, Base
from app.utils import log


@asynccontextmanager
async def get_engine():
    """数据库引擎上下文管理器"""
    try:
        yield engine
    finally:
        await engine.dispose()


async def init_db():
    """初始化数据库表。

    仅用于开发期的快速建表，不替代正式的 Alembic 迁移流程。
    生产环境或结构变更时，请优先使用：
        alembic revision --autogenerate -m "message"
        alembic upgrade head
    """
    log.debug(f"Tables to be created: {Base.metadata.tables.keys()}")

    async with get_engine() as eng:
        async with eng.begin() as conn:
            # 创建所有表
            await conn.run_sync(Base.metadata.create_all)
            log.info("Database tables created successfully!")


if __name__ == "__main__":

    try:
        asyncio.run(init_db())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        import traceback

        traceback.print_exc()
