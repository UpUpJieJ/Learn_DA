"""Docker-based code execution provider."""

from __future__ import annotations

import time
from typing import Protocol
from uuid import uuid4

import docker
from docker.errors import APIError

from runner.schemas import ExecutionStatus, RunnerExecutionRequest
from runner.settings import runner_settings

# Maximum bytes we keep per output stream.
_MAX_OUTPUT = runner_settings.RUNNER_MAX_OUTPUT_BYTES


class ExecutionProvider(Protocol):
    """Minimal interface the HTTP layer depends on."""

    def ping(self) -> bool: ...
    def execute(self, request: RunnerExecutionRequest) -> dict: ...


def _clip(text: str, limit: int = _MAX_OUTPUT) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return text, False
    return encoded[:limit].decode("utf-8", errors="replace"), True


class DockerExecutionProvider:
    """Execute code in a short-lived restricted Docker container."""

    def __init__(
        self,
        *,
        image: str | None = None,
        docker_host: str | None = None,
    ) -> None:
        self._image = image or runner_settings.RUNNER_DOCKER_IMAGE
        self._docker_host = docker_host or runner_settings.RUNNER_DOCKER_HOST
        self._client: docker.DockerClient | None = None

    def _get_client(self) -> docker.DockerClient:
        """Lazily create the Docker client on first use."""
        if self._client is None:
            self._client = docker.DockerClient(base_url=self._docker_host)
        return self._client

    # ------------------------------------------------------------------
    # Protocol
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        try:
            return bool(self._get_client().ping())
        except Exception:
            return False

    def execute(self, request: RunnerExecutionRequest) -> dict:
        execution_id = uuid4()
        start = time.monotonic()
        container = None

        try:
            client = self._get_client()
            container = client.containers.run(
                image=self._image,
                command=["python", "-c", request.code],
                detach=True,
                # Security constraints (Spec §3.2)
                network_mode="none",
                read_only=True,
                user="65532:65532",
                pids_limit=runner_settings.RUNNER_PIDS_LIMIT,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                mem_limit=f"{runner_settings.RUNNER_MEMORY_LIMIT_MB}m",
                nano_cpus=runner_settings.RUNNER_CPU_QUOTA * 10_000,
                tmpfs={"/tmp": f"size={runner_settings.RUNNER_TMPFS_SIZE_MB}m"},
                # Timeout
                auto_remove=False,
            )

            # Wait with a hard timeout.
            wait_result = container.wait(
                timeout=runner_settings.RUNNER_TIMEOUT_SECONDS,
            )
            exit_code: int = wait_result.get("StatusCode", -1)

            # Collect logs.
            raw_logs = container.logs(stdout=True, stderr=True)
            stdout_text, stderr_text = self._split_logs(raw_logs)

            duration_ms = int((time.monotonic() - start) * 1000)

            # Classify status.
            if exit_code == 0:
                status_value = ExecutionStatus.SUCCESS
                error_type = None
            else:
                status_value = ExecutionStatus.ERROR
                error_type = "runtime_error"

            stdout_text, stdout_truncated = _clip(stdout_text)
            stderr_text, stderr_truncated = _clip(stderr_text)

            return {
                "requestId": str(request.request_id),
                "executionId": str(execution_id),
                "status": status_value,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "errorType": error_type,
                "durationMs": duration_ms,
                "outputTruncated": stdout_truncated or stderr_truncated,
            }

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = str(exc).lower()

            if "timeout" in error_msg:
                # Kill the timed-out container.
                if container is not None:
                    try:
                        container.kill()
                    except Exception:
                        pass
                status_value = ExecutionStatus.TIMEOUT
                error_type = "timeout"
            else:
                status_value = ExecutionStatus.ERROR
                error_type = "execution_error"

            return {
                "requestId": str(request.request_id),
                "executionId": str(execution_id),
                "status": status_value,
                "stdout": "",
                "stderr": "",
                "errorType": error_type,
                "durationMs": duration_ms,
                "outputTruncated": False,
            }

        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_logs(raw: bytes) -> tuple[str, str]:
        """Best-effort split of combined stdout+stderr from Docker logs.

        Docker multiplexed log format uses 8-byte headers when using
        ``stdout=True, stderr=True`` together.  For simplicity and test
        predictability the provider requests a single combined stream and
        treats the entire payload as stdout.  A future iteration can
        demultiplex using the 8-byte header protocol.
        """
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = str(raw)
        return text, ""
