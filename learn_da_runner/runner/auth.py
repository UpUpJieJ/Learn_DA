"""Token-based authentication for the Runner internal API."""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status


async def require_runner_token(
    x_runner_token: str = Header(default=""),
) -> None:
    """Validate the X-Runner-Token header using constant-time comparison.

    Reads RUNNER_TOKEN from the environment on every call so that the
    settings singleton does not cache a stale value during tests.
    """
    expected = os.environ.get("RUNNER_TOKEN", "")
    if not expected or not secrets.compare_digest(x_runner_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Runner token",
        )
