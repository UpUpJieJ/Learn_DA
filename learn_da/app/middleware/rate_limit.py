"""
速率限制中间件模块

该模块提供基础的 IP 级别全局限流，防止暴力攻击和滥用。
使用 Redis 滑动窗口算法跟踪每个客户端 IP 的请求频率。

职责划分：
- RateLimitMiddleware（本模块）：基础 IP 级别全局限流
- SlowAPI（装饰器）：业务逻辑级别的精细限流（针对特定端点）
"""

from fastapi import Request, status, FastAPI
from typing import Callable, Dict, Tuple, Any, Optional
import time
import redis.asyncio as redis

from app.core.redis import get_async_redis_client
from config.settings import settings
from app.utils import log
from app.utils.rate_limit_config import RateLimitConfig


class RateLimitSettings:
    """中间件速率限制配置类（仅用于基础 IP 级别限流）"""

    def __init__(self):
        # 全局基础限流配置（按 IP）
        # 这是一个相对宽松的限制，用于防止暴力攻击
        self.GLOBAL_IP_RATE_LIMIT: str = getattr(
            settings,
            'RATE_LIMIT_GLOBAL_IP',
            '200/minute'  # 默认：每个 IP 每分钟 200 请求
        )

        # Redis键前缀（用于速率限制）
        self.REDIS_KEY_PREFIX: str = "global_rate_limit"


class CustomRateLimiter:
    """自定义速率限制器，使用Redis滑动窗口算法实现（仅用于 IP 级别限流）"""

    def __init__(self, redis_client: redis.Redis):
        """
        初始化自定义速率限制器

        Args:
            redis_client: Redis客户端实例
        """
        self.redis_client = redis_client
        self.settings = RateLimitSettings()

    async def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, Dict[str, Any]]:
        """
        检查请求是否被允许（基于速率限制规则）

        Args:
            key: Redis键，用于跟踪请求
            limit: 时间窗口内允许的最大请求数
            window: 时间窗口长度（秒）

        Returns:
            Tuple[bool, Dict]: (是否允许, 速率限制信息字典)
        """
        try:
            import uuid
            current_time = int(time.time())
            window_start = current_time - window

            # 使用pipeline批量执行Redis命令
            pipe = self.redis_client.pipeline()

            # 移除过期的请求记录（基于分数/时间戳）
            pipe.zremrangebyscore(key, 0, window_start)

            # 获取当前窗口内的请求数量
            pipe.zcard(key)

            # 执行前两个命令
            results = await pipe.execute()
            current_requests = results[1]

            # 检查是否超过限制
            if current_requests >= limit:
                # 超过限制，拒绝请求
                info = {
                    "limit": limit,
                    "remaining": 0,
                    "reset": current_time + (window - (current_time % window))
                }
                return False, info

            # 未超过限制，添加当前请求时间戳
            # 使用唯一的 member (UUID) 避免同一秒内的请求互相覆盖
            pipe = self.redis_client.pipeline()
            pipe.zadd(key, {str(uuid.uuid4()): current_time})
            pipe.expire(key, window + 10)  # 添加缓冲时间防止竞态条件
            await pipe.execute()

            # 计算速率限制信息
            info = {
                "limit": limit,
                "remaining": max(0, limit - current_requests - 1),
                "reset": current_time + (window - (current_time % window))
            }

            return True, info

        except Exception as e:
            log.error(f"速率限制检查错误: {e}")
            # Redis不可用时采用"fail open"策略（允许请求通过）
            return True, {"limit": limit, "remaining": limit, "reset": 0}


class RateLimitMiddleware:
    """
    ASGI中间件，用于基础的 IP 级别全局限流

    职责：防止单个 IP 的暴力攻击和滥用
    不负责：业务逻辑级别的精细限流（由 SlowAPI 装饰器处理）
    """

    def __init__(self, app, redis_client: redis.Redis):
        """
        初始化速率限制中间件

        Args:
            app: ASGI应用程序
            redis_client: Redis客户端实例
        """
        self.app = app
        self.limiter = CustomRateLimiter(redis_client)
        self.settings = RateLimitSettings()

    async def __call__(self, scope, receive, send):
        """处理传入的请求并应用基础 IP 级别限流"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # 获取客户端 IP 地址
        client_ip = self._get_client_ip(request)

        # 使用全局 IP 限流配置
        rate_limit = self.settings.GLOBAL_IP_RATE_LIMIT

        # 解析速率限制字符串
        limit_count, period = self._parse_rate_limit(rate_limit)

        # 计算时间窗口（秒）
        window = self._get_window_seconds(period)

        # 创建Redis键（仅基于 IP）
        key = f"{self.settings.REDIS_KEY_PREFIX}:ip:{client_ip}"

        # 检查请求是否被允许
        is_allowed, info = await self.limiter.is_allowed(key, limit_count, window)

        if not is_allowed:
            # 返回429 Too Many Requests响应
            std_resp = RateLimitConfig.create_rate_limit_response(
                endpoint_type="default",
                retry_after=max(1, info["reset"] - int(time.time())),
                detail="基础 IP 限流触发，请降低请求频率"
            )
            response = std_resp.to_response()
            await response(scope, receive, send)
            return

        # 向响应中添加速率限制头信息
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"X-RateLimit-Limit", str(info["limit"]).encode()),
                    (b"X-RateLimit-Remaining", str(info["remaining"]).encode()),
                    (b"X-RateLimit-Reset", str(info["reset"]).encode()),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _get_client_ip(self, request: Request) -> str:
        """
        从请求中提取客户端 IP 地址

        Args:
            request: HTTP请求对象

        Returns:
            str: 客户端 IP 地址
        """
        # 尝试从头部获取真实IP（适用于反向代理设置）
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For可能包含多个IP，取第一个
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        return client_ip

    def _parse_rate_limit(self, rate_limit: str) -> Tuple[int, str]:
        """
        解析速率限制字符串为计数和时间段

        Args:
            rate_limit: 速率限制字符串（例如："100/minute"）

        Returns:
            Tuple[int, str]: (计数, 时间段)
        """
        parts = rate_limit.split("/")
        if len(parts) != 2:
            raise ValueError(f"无效的速率限制格式: {rate_limit}")

        count = int(parts[0])
        period = parts[1]
        return count, period

    def _get_window_seconds(self, period: str) -> int:
        """
        将时间段字符串转换为秒数

        Args:
            period: 时间段字符串（"second", "minute", "hour", "day"）

        Returns:
            int: 对应的秒数
        """
        period_map = {
            "second": 1,
            "minute": 60,
            "hour": 3600,
            "day": 86400
        }
        return period_map.get(period, 60)  # 默认为1分钟


def setup_rate_limit_middleware(app: FastAPI):
    """
    设置全局速率限制中间件
    Args:
        app: FastAPI应用程序
    """
    try:
        redis_client_for_rate_limit = get_async_redis_client()
        app.add_middleware(RateLimitMiddleware, redis_client=redis_client_for_rate_limit)
        log.debug("全局速率限制中间件已初始化")
    except Exception as e:
        log.warning(f"无法初始化速率限制中间件: {e}")
