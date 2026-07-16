"""
Trusted-proxy client IP resolution.

Only trusts X-Forwarded-For when the direct TCP peer is listed in
``trusted_proxy_ips``.  This prevents untrusted clients from spoofing
their IP address through forged forwarding headers.
"""

from __future__ import annotations

from starlette.requests import Request


def get_client_ip(request: Request, trusted_proxy_ips: set[str]) -> str:
    """
    Resolve the real client IP address.

    Parameters
    ----------
    request:
        The incoming Starlette request.
    trusted_proxy_ips:
        Set of IP addresses whose ``X-Forwarded-For`` headers should be trusted.
        Typically this contains the Nginx / load-balancer addresses.

    Returns
    -------
    str
        The resolved client IP, or ``"unknown"`` if it cannot be determined.
    """
    remote_addr = request.client.host if request.client else "unknown"

    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for and remote_addr in trusted_proxy_ips:
        # First IP in the chain is the original client (added by the first
        # trusted proxy).
        return forwarded_for.split(",")[0].strip()

    return remote_addr
