"""
异步Redis客户端
提供常用的Redis异步操作方法，包括字符串、哈希、列表、集合等操作
"""
import asyncio
import json
import hashlib
from typing import Any, AsyncContextManager, Awaitable, Optional, Type, TypeVar, Union, List, Dict, Tuple, Callable
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from redis.asyncio import Redis as AsyncRedis
from .pool import redis_pool_manager
from app.utils.logger import log
from config.settings import settings

T = TypeVar('T', bound=BaseModel)
ModelType = TypeVar('ModelType')
class AsyncRedisClient:
    """异步Redis客户端"""

    def __init__(self, pool_name: str = 'default'):
        self.pool_name = pool_name
        self._async_pool = redis_pool_manager.get_async_pool(pool_name)
        self._key_prefix = (settings.REDIS_CACHE_PREFIX or "").strip(":")

        if self._async_pool is None:
            self._async_pool = redis_pool_manager.create_async_pool(pool_name)

    def _build_key(self, key: str) -> str:
        if not self._key_prefix:
            return key
        prefix = f"{self._key_prefix}:"
        if key.startswith(prefix):
            return key
        return f"{prefix}{key}"

    def _serialize_value(self, value: Any) -> str:
        """序列化值，支持 Pydantic 模型和其他对象"""
        if isinstance(value, (str, int, float)):
            return str(value)
        elif hasattr(value, 'model_dump'):
            # Pydantic v2 模型
            return json.dumps(value.model_dump(), ensure_ascii=False, default=str)
        elif hasattr(value, 'dict'):
            # Pydantic v1 模型
            return json.dumps(value.dict(), ensure_ascii=False, default=str)
        elif isinstance(value, list):
            serialized_list = []
            for item in value:
                if hasattr(item, 'model_dump'):
                    serialized_list.append(item.model_dump())
                elif hasattr(item, 'dict'):
                    serialized_list.append(item.dict())
                elif isinstance(item, (str, int, float, bool, type(None))):
                    serialized_list.append(item)
                else:
                    serialized_list.append(item)
            return json.dumps(serialized_list, ensure_ascii=False, default=str)
        elif isinstance(value, tuple):
            serialized_list = []
            for item in value:
                if hasattr(item, 'model_dump'):
                    serialized_list.append(item.model_dump())
                elif hasattr(item, 'dict'):
                    serialized_list.append(item.dict())
                elif isinstance(item, (str, int, float, bool, type(None))):
                    serialized_list.append(item)
                else:
                    serialized_list.append(item)
            return json.dumps(serialized_list, ensure_ascii=False, default=str)
        elif isinstance(value, dict):
            serialized_dict = {}
            for k, v in value.items():
                if hasattr(v, 'model_dump'):
                    serialized_dict[k] = v.model_dump()
                elif hasattr(v, 'dict'):
                    serialized_dict[k] = v.dict()
                elif isinstance(v, (str, int, float, bool, type(None))):
                    serialized_dict[k] = v
                else:
                    serialized_dict[k] = v
            return json.dumps(serialized_dict, ensure_ascii=False, default=str)
        else:
            # 其他对象
            return json.dumps(value, ensure_ascii=False, default=str)

    def _deserialize_value(self, value: str) -> Any:
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value


    async def set(self, key: str, value: Any, expire: Optional[int] = None,
                  nx: bool = False, xx: bool = False) -> bool:
        """
            key: 键
            value: 值
            expire: 过期时间(秒)
            nx: 仅当键不存在时设置
            xx: 仅当键存在时设置
        """
        try:
            # 序列化值
            key = self._build_key(key)
            if not isinstance(value, (str, int, float)):
                value = self._serialize_value(value)

            async with AsyncRedis(connection_pool=self._async_pool) as client:
                result = await client.set(
                    key, value, ex=expire, nx=nx, xx=xx
                )
            return bool(result)
        except Exception as e:
            log.error(f"Redis SET 错误: {e}")
            return False

    async def set_with_logical_expire(self, key: str, value: Any, expire: int) -> bool:
        """逻辑过期设置缓存"""
        try:
            key = self._build_key(key)
            if not isinstance(value, (str, int, float)):
                value = self._serialize_value(value)
            # 使用时间戳代替 datetime 对象，避免 JSON 序列化问题
            expire_timestamp = (datetime.now(timezone(timedelta(hours=8))) + timedelta(seconds=expire)).timestamp()
            data_dict = {"data": value, "expire": expire_timestamp}
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                result = await client.set(
                    key, json.dumps(data_dict, ensure_ascii=False, default=str),
                )
            return bool(result)
        except Exception as e:
            log.error(f"Redis SET 错误: {e}")
            return False        

    async def get_with_logical_expire(self, key: str) -> tuple[Any, datetime] | None:
        try:
            key = self._build_key(key)
            data_dict = await self.get(key)
            # 缓存不存在
            if data_dict is None:
                return None
            data_dict["data"] = self._deserialize_value(data_dict["data"])
            # 将时间戳转换回 datetime 对象
            expire_time = datetime.fromtimestamp(data_dict["expire"], tz=timezone(timedelta(hours=8)))
            return data_dict["data"], expire_time
        except Exception as e:
            log.error(f"Redis GET 错误: {e}")
            return None
        
    async def refresh_logical_expire_cache(
        self,
        key: str,
        id: int,
        expire: int,
        pydantic_type: Type[BaseModel],
        query_func: Callable[..., Awaitable[Optional[ModelType]]],
        session_factory: Optional[Callable[[], AsyncContextManager[Any]]] = None
    ) -> None:
        """
        刷新逻辑过期缓存

        Args:
            key: 缓存键
            id: 查询ID
            expire: 过期时间(秒)
            query_func: 查询函数，接收 id 参数
            session_factory: 会话工厂函数，用于在后台任务中创建新的数据库会话
        """
        async def _do_refresh():
            if session_factory:
                # 使用会话工厂创建新会话
                async with session_factory() as session:
                    data = await query_func(id, session)
            else:
                data = await query_func(id)

            if data is not None:
                res = pydantic_type.model_validate(data)
                await self.set_with_logical_expire(key, res, expire)

        try:
            await _do_refresh()
        except Exception as e:
            log.error(f"刷新逻辑过期缓存失败: {e}")


    async def query_with_pass_through_cache(
        self,
        key: str,
        id: int,
        pydantic_type: Type[T],
        query_func: Callable[[int], Awaitable[Optional[ModelType]]],
        expire: int
    ) -> Optional[T]:
        """
        空值解决缓存穿透
        """
        cached = await self.get(key)
        if cached:
            if cached == "null_data":
                return None
            return cached
    
        data = await query_func(id)
        if data is None:
            await self.set(key, "null_data", expire=settings.REDIS_CACHE_NULL_EXPIRE)
            return None
        result = pydantic_type.model_validate(data)
        await self.set(key, result, expire=expire)
        return result
    

    async def query_with_logical_expire_cache(
        self,
        key: str,
        id: int,
        pydantic_type: Type[T],
        query_func: Callable[..., Awaitable[Optional[ModelType]]],
        expire: int,
        session_factory: Optional[Callable[[], AsyncContextManager[Any]]] = None
    ) -> Optional[T]:
        """
        使用逻辑过期解决缓存击穿问题
        注意：如果缓存不存在，会查询数据库并写入缓存
        """
        # 直接调用 get_with_logical_expire，避免重复 Redis 调用
        result = await self.get_with_logical_expire(key)
        
        if result is None:
            # 缓存不存在，查询数据库
            if session_factory:
                async with session_factory() as session:
                    data = await query_func(id, session)
            else:
                data = await query_func(id)
            if data is None:
                return None
            # 写入缓存并返回
            res = pydantic_type.model_validate(data)
            await self.set_with_logical_expire(key, res, expire)
            return res
        
        data, expire_time = result
        
        # 已过期：尝试获取锁并后台刷新
        if expire_time < datetime.now(timezone(timedelta(hours=8))):
            lock_name = f"logic:{key}"
            lock_id = await self.acquire_lock(lock_name, timeout=10, blocking_timeout=0)
            if lock_id:
                task = asyncio.create_task(
                    self.refresh_logical_expire_cache(key, id, expire, pydantic_type, query_func, session_factory=session_factory))
                task.add_done_callback(self._handle_background_task_error)
        
        return pydantic_type.model_validate(data)

    def _handle_background_task_error(self, task: asyncio.Task) -> None:
        """处理后台任务的异常"""
        try:
            if task.exception():
                log.error(f"后台任务执行失败: {task.exception()}")
        except asyncio.CancelledError:
            pass  # 任务被取消时忽略

    async def get(self, key: str, default: Any = None) -> Any:
        try:
            key = self._build_key(key)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                value = await client.get(key)

            if value is None:
                return default

            return self._deserialize_value(value)
        except Exception as e:
            log.error(f"Redis GET 错误: {e}")
            return default

    async def mget(self, keys: List[str]) -> List[Any]:
        try:
            keys = [self._build_key(key) for key in keys]
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                values = await client.mget(keys)

            result = []
            for value in values:
                if value is None:
                    result.append(None)
                else:
                    result.append(self._deserialize_value(value))
            return result
        except Exception as e:
            log.error(f"Redis MGET 错误: {e}")
            return [None] * len(keys)

    async def delete(self, *keys: str) -> int:
        try:
            keys = tuple(self._build_key(key) for key in keys)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return await client.delete(*keys)
        except Exception as e:
            log.error(f"Redis DEL 错误: {e}")
            return 0

    async def delete_pattern(self, pattern: str) -> int:
        try:
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                # 获取所有匹配的键
                pattern = self._build_key(pattern)
                keys = await client.keys(pattern)
                if keys:
                    # 批量删除
                    return await client.delete(*keys)
                return 0
        except Exception as e:
            log.error(f"Redis DEL_PATTERN 错误: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        try:
            key = self._build_key(key)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return bool(await client.exists(key))
        except Exception as e:
            log.error(f"Redis EXISTS 错误: {e}")
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        try:
            key = self._build_key(key)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return bool(await client.expire(key, seconds))
        except Exception as e:
            log.error(f"Redis EXPIRE 错误: {e}")
            return False

    async def ttl(self, key: str) -> int:
        try:
            key = self._build_key(key)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return await client.ttl(key)
        except Exception as e:
            log.error(f"Redis TTL 错误: {e}")
            return -2


    async def hset(self, name: str, mapping: Dict[str, Any],
                   expire: Optional[int] = None) -> int:
        try:
            # 序列化值
            name = self._build_key(name)
            serialized_mapping = {}
            for k, v in mapping.items():
                if isinstance(v, (str, int, float)):
                    serialized_mapping[k] = str(v)
                else:
                    serialized_mapping[k] = self._serialize_value(v)

            async with AsyncRedis(connection_pool=self._async_pool) as client:
                result = await client.hset(name, mapping=serialized_mapping)

                if expire:
                    await client.expire(name, expire)

                return result
        except Exception as e:
            log.error(f"Redis HSET 错误: {e}")
            return 0

    async def hget(self, name: str, key: str) -> Any:
        try:
            name = self._build_key(name)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                value = await client.hget(name, key)

            if value is None:
                return None

            return self._deserialize_value(value)
        except Exception as e:
            log.error(f"Redis HGET 错误: {e}")
            return None

    async def hgetall(self, name: str) -> Dict[str, Any]:
        try:
            name = self._build_key(name)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                hash_dict = await client.hgetall(name)

            result = {}
            for k, v in hash_dict.items():
                result[k] = self._deserialize_value(v)
            return result
        except Exception as e:
            log.error(f"Redis HGETALL 错误: {e}")
            return {}

    async def hdel(self, name: str, *keys: str) -> int:
        try:
            name = self._build_key(name)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return await client.hdel(name, *keys)
        except Exception as e:
            log.error(f"Redis HDEL 错误: {e}")
            return 0


    async def lpush(self, name: str, *values: Any) -> int:
        try:
            # 序列化值
            name = self._build_key(name)
            serialized_values = []
            for v in values:
                if isinstance(v, str):
                    serialized_values.append(v)
                else:
                    serialized_values.append(self._serialize_value(v))

            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return await client.lpush(name, *serialized_values)
        except Exception as e:
            log.error(f"Redis LPUSH 错误: {e}")
            return 0

    async def rpush(self, name: str, *values: Any) -> int:
        try:
            # 序列化值
            name = self._build_key(name)
            serialized_values = []
            for v in values:
                if isinstance(v, str):
                    serialized_values.append(v)
                else:
                    serialized_values.append(self._serialize_value(v))

            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return await client.rpush(name, *serialized_values)
        except Exception as e:
            log.error(f"Redis RPUSH 错误: {e}")
            return 0

    async def lpop(self, name: str) -> Any:
        try:
            name = self._build_key(name)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                value = await client.lpop(name)

            if value is None:
                return None

            return self._deserialize_value(value)
        except Exception as e:
            log.error(f"Redis LPOP 错误: {e}")
            return None

    async def rpop(self, name: str) -> Any:
        try:
            name = self._build_key(name)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                value = await client.rpop(name)

            if value is None:
                return None

            return self._deserialize_value(value)
        except Exception as e:
            log.error(f"Redis RPOP 错误: {e}")
            return None

    async def lrange(self, name: str, start: int = 0, end: int = -1) -> List[Any]:
        try:
            name = self._build_key(name)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                values = await client.lrange(name, start, end)

            result = []
            for value in values:
                result.append(self._deserialize_value(value))
            return result
        except Exception as e:
            log.error(f"Redis LRANGE 错误: {e}")
            return []

    async def llen(self, name: str) -> int:
        try:
            name = self._build_key(name)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return await client.llen(name)
        except Exception as e:
            log.error(f"Redis LLEN 错误: {e}")
            return 0


    async def sadd(self, name: str, *values: Any) -> int:
        try:
            # 序列化值
            serialized_values = []
            for v in values:
                if isinstance(v, str):
                    serialized_values.append(v)
                else:
                    serialized_values.append(self._serialize_value(v))

            name = self._build_key(name)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return await client.sadd(name, *serialized_values)
        except Exception as e:
            log.error(f"Redis SADD 错误: {e}")
            return 0

    async def smembers(self, name: str) -> set:
        try:
            name = self._build_key(name)
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                members = await client.smembers(name)

            result = set()
            for member in members:
                result.add(self._deserialize_value(member))
            return result
        except Exception as e:
            log.error(f"Redis SMEMBERS 错误: {e}")
            return set()

    async def srem(self, name: str, *values: Any) -> int:
        try:
            # 序列化值
            name = self._build_key(name)
            serialized_values = []
            for v in values:
                if isinstance(v, str):
                    serialized_values.append(v)
                else:
                    serialized_values.append(self._serialize_value(v))

            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return await client.srem(name, *serialized_values)
        except Exception as e:
            log.error(f"Redis SREM 错误: {e}")
            return 0

    async def sismember(self, name: str, value: Any) -> bool:
        try:
            # 序列化值
            name = self._build_key(name)
            if not isinstance(value, str):
                value = self._serialize_value(value)

            async with AsyncRedis(connection_pool=self._async_pool) as client:
                return await client.sismember(name, value)
        except Exception as e:
            log.error(f"Redis SISMEMBER 错误: {e}")
            return False


    async def acquire_lock(self, name: str, timeout: int = 10,
                           blocking_timeout: Optional[int] = None) -> Optional[str]:
        """
        获取分布式锁
            name: 锁名称
            timeout: 锁超时时间(秒)
            blocking_timeout: 阻塞等待超时时间(秒)
        """
        import uuid
        identifier = str(uuid.uuid4())
        lock_key = self._build_key(f"lock:{name}")

        end = None
        if blocking_timeout:
            end = datetime.now(timezone(timedelta(hours=8))) + timedelta(seconds=blocking_timeout)

        while True:
            try:
                async with AsyncRedis(connection_pool=self._async_pool) as client:
                    acquired = await client.set(
                        lock_key, identifier, nx=True, ex=timeout
                    )

                if acquired:
                    return identifier

                if end and datetime.now(timezone(timedelta(hours=8))) >= end:
                    return None

                import asyncio
                await asyncio.sleep(0.001)
            except Exception as e:
                log.error(f"Redis 获取锁错误: {e}")
                return None

    async def release_lock(self, name: str, identifier: str) -> bool:
        """
        释放分布式锁
            name: 锁名称
            identifier: 锁标识符
        """


        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        try:
            lock_key = self._build_key(f"lock:{name}")
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                result = await client.eval(
                    lua_script, 1, lock_key, identifier
                )
            return bool(result)
        except Exception as e:
            log.error(f"Redis 释放锁错误: {e}")
            return False

    async def flushdb(self) -> bool:
        try:
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                await client.flushdb()
            return True
        except Exception as e:
            log.error(f"Redis FLUSHDB 错误: {e}")
            return False

    async def info(self) -> Dict[str, Any]:
        try:
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                info = await client.info()
            return info
        except Exception as e:
            log.error(f"Redis INFO 错误: {e}")
            return {}

    async def ping(self) -> bool:
        try:
            async with AsyncRedis(connection_pool=self._async_pool) as client:
                await client.ping()
            return True
        except Exception as e:
            log.error(f"Redis PING 错误: {e}")
            return False
