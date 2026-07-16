"""Runner HTTP service — internal API for the Learn DA backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Generator

import anyio
from fastapi import Depends, FastAPI, HTTPException, status

from runner.auth import require_runner_token
from runner.provider import DockerExecutionProvider, ExecutionProvider
from runner.schemas import RunnerExecutionRequest, RunnerExecutionResult
from runner.settings import runner_settings

_provider: ExecutionProvider | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _provider
    _provider = DockerExecutionProvider()
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
    """Readiness — checks that the Docker provider is reachable."""
    if not provider.ping():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker provider unhealthy",
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
