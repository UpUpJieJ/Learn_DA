"""
Redis连接池管理器
提供异步 Redis 连接池的创建、管理和配置功能
"""

from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from redis.asyncio import ConnectionPool as AsyncConnectionPool, Redis as AsyncRedis
from app.utils.logger import log
from config.settings import settings


class RedisPoolManager:
    """Redis连接池管理器（异步）"""

    _instance: Optional['RedisPoolManager'] = None
    _async_pools: Dict[str, AsyncConnectionPool] = {}

    @staticmethod
    def get_redis_config() -> Dict[str, Any]:
        """
        获取Redis连接配置

        Returns:
            Dict[str, Any]: Redis配置字典
        """
        config = {
            'host': settings.REDIS_HOST,
            'port': settings.REDIS_PORT,
            'db': settings.REDIS_DB,
            'decode_responses': True,
            'socket_connect_timeout': settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            'socket_timeout': settings.REDIS_SOCKET_TIMEOUT,
            'retry_on_timeout': settings.REDIS_RETRY_ON_TIMEOUT,
            'health_check_interval': settings.REDIS_HEALTH_CHECK_INTERVAL,
            'max_connections': settings.REDIS_MAX_CONNECTIONS,
        }

        if settings.REDIS_PASSWORD:
            config['password'] = settings.REDIS_PASSWORD

        return config

    def __new__(cls) -> 'RedisPoolManager':
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化连接池管理器"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._config = self.get_redis_config()
            log.debug("RedisPoolManager 实例已创建")

    def create_async_pool(self, name: str = 'default', **kwargs) -> AsyncConnectionPool:
        """
        创建异步Redis连接池

        Args:
            name: 连接池名称
            **kwargs: 连接池配置参数

        Returns:
            AsyncConnectionPool: 异步Redis连接池实例
        """
        if name in self._async_pools:
            return self._async_pools[name]

        config = self._config.copy()
        config.update(kwargs)

        try:
            pool = AsyncConnectionPool(**config)
            self._async_pools[name] = pool
            log.debug(f"异步Redis连接池 '{name}' 创建成功")
            return pool
        except Exception as e:
            log.error(f"创建异步Redis连接池 '{name}' 失败: {e}")
            raise

    def get_async_pool(self, name: str = 'default') -> Optional[AsyncConnectionPool]:
        """获取异步Redis连接池"""
        return self._async_pools.get(name)

    def close_pool(self, name: str):
        """关闭指定的异步 Redis 连接池"""
        if name in self._async_pools:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._async_pools[name].disconnect())
                else:
                    loop.run_until_complete(self._async_pools[name].disconnect())
            except Exception as e:
                log.error(f"关闭异步Redis连接池 '{name}' 时出错: {e}")
            finally:
                del self._async_pools[name]
                log.info(f"异步Redis连接池 '{name}' 已关闭")

    def close_all_pools(self):
        """关闭所有异步 Redis 连接池"""
        for name in list(self._async_pools.keys()):
            self.close_pool(name)
        log.info("所有Redis连接池已关闭")

    async def test_connection(self, name: str = 'default') -> bool:
        """测试异步连接池连接是否正常"""
        pool = self.get_async_pool(name)
        if not pool:
            pool = self.create_async_pool(name)
        try:
            async with AsyncRedis(connection_pool=pool) as client:
                await client.ping()
            log.info(f"异步Redis连接池 '{name}' 连接测试成功")
            return True
        except Exception as e:
            log.error(f"异步Redis连接池 '{name}' 连接测试失败: {e}")
            return False

    @asynccontextmanager
    async def get_redis_client(self, name: str = 'default'):
        """
        获取异步Redis客户端的上下文管理器

        Args:
            name: 连接池名称
        """
        pool = self.get_async_pool(name)
        if not pool:
            pool = self.create_async_pool(name)

        client = AsyncRedis(connection_pool=pool)
        try:
            yield client
        finally:
            await client.close()

    def get_async_redis_client(self, name: str = 'default') -> AsyncRedis:
        """
        获取原生异步Redis客户端（用于中间件等需要原生客户端的场景）

        Args:
            name: 连接池名称

        Returns:
            AsyncRedis: 原生异步Redis客户端实例
        """
        pool = self.get_async_pool(name)
        if not pool:
            pool = self.create_async_pool(name)
        return AsyncRedis(connection_pool=pool)


redis_pool_manager = RedisPoolManager()