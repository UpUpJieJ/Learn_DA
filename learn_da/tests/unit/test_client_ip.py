"""
Tests for trusted-proxy client IP resolution.

Run with: uv run pytest tests/unit/test_client_ip.py -q
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core.client_ip import get_client_ip


def _make_request(
    remote_addr: str = "127.0.0.1",
    x_forwarded_for: str | None = None,
) -> Request:
    scope = {
        "type": "http",
        "client": (remote_addr, 12345),
        "headers": [],
    }
    if x_forwarded_for:
        scope["headers"] = [
            (b"x-forwarded-for", x_forwarded_for.encode()),
        ]
    return Request(scope)


# ── Direct client (no proxy header) ──────────────────────


def test_direct_client_returns_remote_addr():
    req = _make_request(remote_addr="1.2.3.4")
    assert get_client_ip(req, trusted_proxy_ips=set()) == "1.2.3.4"


# ── Trusted proxy ─────────────────────────────────────────


def test_trusted_proxy_uses_first_forwarded_ip():
    req = _make_request(remote_addr="10.0.0.1", x_forwarded_for="203.0.113.50, 70.41.3.18")
    assert get_client_ip(req, trusted_proxy_ips={"10.0.0.1"}) == "203.0.113.50"


def test_trusted_proxy_strips_whitespace():
    req = _make_request(remote_addr="10.0.0.1", x_forwarded_for=" 203.0.113.50 ")
    assert get_client_ip(req, trusted_proxy_ips={"10.0.0.1"}) == "203.0.113.50"


# ── Untrusted proxy ───────────────────────────────────────


def test_untrusted_proxy_ignores_forwarded_for():
    """When the direct client is NOT in trusted_proxy_ips, X-Forwarded-For is ignored."""
    req = _make_request(remote_addr="99.99.99.99", x_forwarded_for="1.1.1.1")
    assert get_client_ip(req, trusted_proxy_ips={"10.0.0.1"}) == "99.99.99.99"


def test_empty_trusted_set_never_trusts_forwarded():
    req = _make_request(remote_addr="10.0.0.1", x_forwarded_for="spoofed-ip")
    assert get_client_ip(req, trusted_proxy_ips=set()) == "10.0.0.1"


# ── Edge cases ────────────────────────────────────────────


def test_missing_client_returns_unknown():
    scope = {"type": "http", "client": None, "headers": []}
    req = Request(scope)
    assert get_client_ip(req, trusted_proxy_ips=set()) == "unknown"


def test_forwarded_for_empty_string_treated_as_missing():
    req = _make_request(remote_addr="1.2.3.4", x_forwarded_for="")
    assert get_client_ip(req, trusted_proxy_ips={"1.2.3.4"}) == "1.2.3.4"
