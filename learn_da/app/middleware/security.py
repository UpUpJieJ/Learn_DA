"""
Environment-aware security headers middleware.

Production:
- Content-Security-Policy (strict)
- Strict-Transport-Security
- Permissions-Policy
- X-Content-Type-Options
- Referrer-Policy

Development:
- Same X-Content-Type-Options and Referrer-Policy (safe defaults)
- No HSTS or strict CSP (to avoid dev-server issues)
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from config.settings import settings

# ── Production CSP ────────────────────────────────────────

_PRODUCTION_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-related HTTP response headers."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Always safe
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if settings.APP_ENV == "production":
            response.headers["Content-Security-Policy"] = _PRODUCTION_CSP
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
            response.headers["Permissions-Policy"] = (
                "camera=(), microphone=(), geolocation=()"
            )

        # X-XSS-Protection is deprecated — intentionally omitted.
        # X-Frame-Options replaced by CSP frame-ancestors in production.

        return response


def setup_security_middleware(app):
    """Register the security headers middleware."""
    app.add_middleware(SecurityHeadersMiddleware)
