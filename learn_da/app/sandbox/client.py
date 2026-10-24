"""HTTP client for the isolated Runner service."""

from __future__ import annotations

import logging
from uuid import uuid4

import httpx

from app.sandbox.schemas import (
    ExecutionStatus,
    RunnerExecutionRequest,
    SandboxExecutionResult,
)
from config.settings import settings

log = logging.getLogger(__name__)


class RunnerUnavailableError(Exception):
    """Raised when the Runner cannot be reached or returns an infrastructure error."""

    pass


class RunnerClient:
    """Thin async wrapper around the Runner HTTP API."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        runner_settings=None,
    ) -> None:
        self._http = http_client
        resolved = runner_settings or settings
        self._base_url = resolved.RUNNER_URL.rstrip("/")
        self._token = resolved.RUNNER_TOKEN
        self._timeout = resolved.RUNNER_TIMEOUT_SECONDS
        # 工作区整段重放用单独的超时；缺字段时回落到单格超时而不是硬编码常数，
        # 这样任何注入的 runner_settings 替身都不会被静默忽略。
        self._session_timeout = float(
            getattr(resolved, "RUNNER_SESSION_TIMEOUT_SECONDS", self._timeout)
        )

    async def execute(
        self,
        payload: RunnerExecutionRequest,
    ) -> SandboxExecutionResult:
        """Send code to the Runner and return the standardised result.

        Any transport or protocol failure raises ``RunnerUnavailableError``.
        """
        try:
            response = await self._http.post(
                f"{self._base_url}/v1/executions",
                headers={"X-Runner-Token": self._token},
                json=payload.model_dump(mode="json", by_alias=True),
                timeout=self._timeout,
            )
            if response.status_code == 503:
                raise RunnerUnavailableError("runner unavailable")
            response.raise_for_status()
            return SandboxExecutionResult.model_validate(response.json())
        except RunnerUnavailableError:
            raise
        except Exception as exc:
            raise RunnerUnavailableError("runner unavailable") from exc

    async def execute_session(self, payload: dict) -> dict:
        """Replay a whole cell list on the Runner (workspace M1).

        The payload is passed through as-is because the session contract lives in
        the workspace module; only the transport concerns are handled here.
        """
        timeout = self._session_timeout
        try:
            response = await self._http.post(
                f"{self._base_url}/v1/sessions",
                headers={"X-Runner-Token": self._token},
                json=payload,
                timeout=timeout,
            )
            if response.status_code == 503:
                raise RunnerUnavailableError("runner unavailable")
            response.raise_for_status()
            return response.json()
        except RunnerUnavailableError:
            raise
        except Exception as exc:
            raise RunnerUnavailableError("runner unavailable") from exc

    async def is_ready(self) -> bool:
        """Check whether the Runner reports readiness."""
        try:
            response = await self._http.get(
                f"{self._base_url}/ready",
                headers={"X-Runner-Token": self._token},
                timeout=3.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._http.aclose()
