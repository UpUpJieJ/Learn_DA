"""
Middleware package for the FastAPI application.

This package contains middleware implementations for:
- CORS (Cross-Origin Resource Sharing) handling
- Rate limiting to prevent abuse
- Access logging for request tracking
- Security headers for protection

The middleware is organized into separate modules for better maintainability.
"""

from app.middleware.cors import setup_cors_middleware, CORSSettings

from app.middleware.rate_limit import (
    RateLimitMiddleware,
    RateLimitSettings,
    CustomRateLimiter
)

from app.middleware.access_log import AccessLogMiddleware, setup_access_log_middleware

__all__ = [
    "setup_cors_middleware",
    "CORSSettings",
    "RateLimitMiddleware",
    "RateLimitSettings",
    "CustomRateLimiter",
    "AccessLogMiddleware",
    "setup_access_log_middleware",
]