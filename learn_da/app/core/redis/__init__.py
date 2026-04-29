"""
Redis module.
Provides shared Redis clients and pool manager.
"""

from .async_client import AsyncRedisClient
from .pool import redis_pool_manager

__all__ = [
    "AsyncRedisClient",
    "redis_pool_manager",
    "get_async_redis_client",
]


def get_async_redis_client(name: str = "default"):
    return redis_pool_manager.get_async_redis_client(name)
