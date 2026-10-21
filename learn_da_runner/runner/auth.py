"""Token-based authentication for the Runner internal API."""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status

from runner.settings import runner_settings


async def require_runner_token(
    x_runner_token: str = Header(default=""),
) -> None:
    """Validate the X-Runner-Token header using constant-time comparison.

    The expected token is resolved per call: the process environment wins (that
    is how the container receives it), then whatever ``.env`` supplied — so a
    local run that only has a ``.env`` file authenticates too, and tests never
    see a stale cached value.
    """
    expected = os.environ.get("RUNNER_TOKEN") or runner_settings.RUNNER_TOKEN
    if not expected or not secrets.compare_digest(x_runner_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Runner token",
        )
