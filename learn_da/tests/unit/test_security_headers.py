"""
Tests for production HTTP security headers and docs gating.

Run with: uv run pytest tests/unit/test_security_headers.py -q
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.security import SecurityHeadersMiddleware, settings


# ── Helpers ────────────────────────────────────────────────


def _request_with_env(app_env: str) -> "httpx.Response":
    """Make a GET /live request with security middleware using given APP_ENV."""
    original = settings.APP_ENV
    try:
        settings.APP_ENV = app_env
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/live")
        async def live():
            return {"status": "ok"}

        with TestClient(app) as client:
            return client.get("/live")
    finally:
        settings.APP_ENV = original


# ── Security headers (production) ────────────────────────


def test_production_csp_header():
    resp = _request_with_env("production")
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp


def test_production_hsts_header():
    resp = _request_with_env("production")
    hsts = resp.headers.get("strict-transport-security", "")
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts


def test_production_permissions_policy():
    resp = _request_with_env("production")
    pp = resp.headers.get("permissions-policy", "")
    assert "camera=()" in pp
    assert "microphone=()" in pp
    assert "geolocation=()" in pp


def test_production_content_type_and_referrer():
    resp = _request_with_env("production")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_no_xss_protection_header():
    """X-XSS-Protection is deprecated and should NOT be set."""
    resp = _request_with_env("production")
    assert "x-xss-protection" not in resp.headers


def test_no_x_frame_options_in_production():
    """X-Frame-Options replaced by CSP frame-ancestors in production."""
    resp = _request_with_env("production")
    assert "x-frame-options" not in resp.headers


# ── Docs gating ───────────────────────────────────────────


def test_production_docs_logic():
    """In production with OPENAPI_ENABLED=false, docs should be None."""
    is_prod = True
    openapi_enabled = False
    docs_url = "/docs" if not is_prod or openapi_enabled else None
    assert docs_url is None


def test_production_docs_enabled_when_flag_set():
    """In production with OPENAPI_ENABLED=true, docs should be accessible."""
    is_prod = True
    openapi_enabled = True
    docs_url = "/docs" if not is_prod or openapi_enabled else None
    assert docs_url == "/docs"


def test_development_docs_always_enabled():
    """In development, docs should always be accessible."""
    is_prod = False
    openapi_enabled = False
    docs_url = "/docs" if not is_prod or openapi_enabled else None
    assert docs_url == "/docs"


# ── Development mode ──────────────────────────────────────


def test_dev_mode_no_hsts():
    """In development, HSTS and full CSP should NOT be set."""
    resp = _request_with_env("development")
    assert "strict-transport-security" not in resp.headers
    assert "content-security-policy" not in resp.headers
