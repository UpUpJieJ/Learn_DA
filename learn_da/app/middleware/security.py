from fastapi import Request, FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    添加安全相关的 HTTP 响应头的中间件
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # 防止点击劫持
        response.headers["X-Frame-Options"] = "DENY"

        # 启用浏览器的 XSS 过滤
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 防止浏览器猜测内容类型
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 严格传输安全 (HSTS) - 生产环境建议开启
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # 引用策略
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 内容安全策略 (CSP) - 根据需求调整
        # response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; object-src 'none';"

        return response


def setup_security_middleware(app: FastAPI):
    """
    将安全中间件添加到 FastAPI 应用程序中
    """
    app.add_middleware(SecurityHeadersMiddleware)
