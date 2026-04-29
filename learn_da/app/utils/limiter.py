"""
速率限制器模块

提供全局共享的 Limiter 实例，避免循环导入问题。
所有路由都使用同一个 limiter 实例进行限流。
"""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import Request
from starlette.responses import JSONResponse

from app.utils.rate_limit_config import RateLimitExceptionHandlers
from app.utils import log
# 创建全局共享的 limiter 实例
# 所有路由模块都应该从这里导入 limiter
limiter = Limiter(key_func=get_remote_address)


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    处理速率限制超限异常，返回项目的统一响应格式

    Args:
        request: 传入的HTTP请求
        exc: RateLimitExceeded异常实例

    Returns:
        JSONResponse: 项目的统一响应格式
    """
    # 使用统一的异常处理器
    std_resp = await RateLimitExceptionHandlers.handle_rate_limit_exceeded(request, exc)
    return std_resp.to_response()


def setup_limiter_middleware(app):
    """
    将limiter挂载到FastAPI app，并注册异常处理器

    Args:
        app: FastAPI实例
    """
    # 挂载limiter到app.state
    app.state.limiter = limiter
    # 注册自定义异常处理器
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
    log.debug("limiter中间件已初始化")
