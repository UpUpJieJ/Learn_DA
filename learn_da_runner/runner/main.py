"""Runner HTTP service — internal API for the Learn DA backend."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Generator

import anyio
from fastapi import Depends, FastAPI, HTTPException, status

from runner.auth import require_runner_token
from runner.local_provider import LocalSubprocessProvider
from runner.provider import DockerExecutionProvider, ExecutionProvider
from runner.schemas import (
    RunnerExecutionRequest,
    RunnerExecutionResult,
    RunnerSessionRequest,
    RunnerSessionResult,
)
from runner.settings import runner_settings

_provider: ExecutionProvider | None = None


def build_provider() -> ExecutionProvider:
    """Select the execution backend from configuration.

    Local execution is a development escape hatch: it needs an explicit opt-in
    and is refused outright in a production environment.
    """
    name = runner_settings.RUNNER_PROVIDER.strip().lower()

    if name == "docker":
        return DockerExecutionProvider()

    if name == "local":
        if not runner_settings.RUNNER_ALLOW_LOCAL_EXECUTION:
            raise RuntimeError(
                "RUNNER_PROVIDER=local requires RUNNER_ALLOW_LOCAL_EXECUTION=1"
            )
        environment = (
            runner_settings.RUNNER_ENV or os.environ.get("APP_ENV", "")
        ).strip().lower()
        if environment == "production":
            raise RuntimeError(
                "RUNNER_PROVIDER=local is refused in production; use docker"
            )
        return LocalSubprocessProvider()

    raise RuntimeError(f"Unknown RUNNER_PROVIDER: {name!r}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _provider
    _provider = build_provider()
    yield
    _provider = None


app = FastAPI(
    title="Learn DA Runner",
    version="0.1.0",
    docs_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


def get_provider() -> ExecutionProvider:
    if _provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runner provider not initialised",
        )
    return _provider


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


@app.get("/live")
async def liveness() -> dict:
    """Process liveness — never calls Docker."""
    return {"status": "ok"}


@app.get("/ready")
async def readiness(
    provider: ExecutionProvider = Depends(get_provider),
) -> dict:
    """Readiness — checks that the configured execution provider is reachable."""
    if not provider.ping():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution provider unhealthy",
        )
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@app.post("/v1/executions", response_model=RunnerExecutionResult)
async def execute(
    payload: RunnerExecutionRequest,
    _: None = Depends(require_runner_token),
    provider: ExecutionProvider = Depends(get_provider),
) -> RunnerExecutionResult:
    """Execute code in a sandboxed container and return the result."""
    raw_result = await anyio.to_thread.run_sync(provider.execute, payload)
    return RunnerExecutionResult.model_validate(raw_result)


@app.post("/v1/sessions", response_model=RunnerSessionResult)
async def execute_session(
    payload: RunnerSessionRequest,
    _: None = Depends(require_runner_token),
    provider: ExecutionProvider = Depends(get_provider),
) -> RunnerSessionResult:
    """Replay a whole cell list in one sandbox and evaluate its assertions."""
    raw_result = await anyio.to_thread.run_sync(provider.execute_session, payload)
    return RunnerSessionResult.model_validate(raw_result)
