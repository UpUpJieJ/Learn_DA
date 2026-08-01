"""
Middleware package for the FastAPI application.

This package contains middleware implementations for:
- CORS (Cross-Origin Resource Sharing) handling
- Access logging for request tracking
- Security headers for protection

The middleware is organized into separate modules for better maintainability.
限流统一由 SlowAPI（app/utils/limiter.py）实现。
"""

from app.middleware.cors import setup_cors_middleware, CORSSettings

from app.middleware.access_log import AccessLogMiddleware, setup_access_log_middleware

__all__ = [
    "setup_cors_middleware",
    "CORSSettings",
    "AccessLogMiddleware",
    "setup_access_log_middleware",
]
