"""Docker-based code execution provider."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import docker
from docker.errors import APIError

from runner.schemas import (
    ExecutionStatus,
    RunnerExecutionRequest,
    RunnerSessionRequest,
)
from runner.session import (
    DRIVER_FILENAME,
    SessionWorkspaceError,
    build_result,
    parse_driver_output,
    prepare_workspace,
)
from runner.session_driver import MARKER
from runner.settings import runner_settings

# Maximum bytes we keep per output stream.
_MAX_OUTPUT = runner_settings.RUNNER_MAX_OUTPUT_BYTES

# Where the prepared workspace is mounted inside the sandbox container.
_SESSION_MOUNT = "/work"


class ExecutionProvider(Protocol):
    """Minimal interface the HTTP layer depends on."""

    def ping(self) -> bool: ...
    def execute(self, request: RunnerExecutionRequest) -> dict: ...
    def execute_session(self, request: RunnerSessionRequest) -> dict: ...


def _clip(text: str, limit: int = _MAX_OUTPUT) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return text, False
    return encoded[:limit].decode("utf-8", errors="replace"), True


def _relax_permissions(root: Path) -> None:
    """Make the prepared workspace readable by the sandbox user (uid 65532)."""
    try:
        root.chmod(0o755)
        for path in root.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
    except OSError:  # pragma: no cover - platform dependent (Windows is a no-op)
        pass


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
    # Session execution (replay-style)
    # ------------------------------------------------------------------

    def execute_session(self, request: RunnerSessionRequest) -> dict:
        """Replay the cell list inside one container, mounted read-only at /work."""
        execution_id = uuid4()
        start = time.monotonic()
        container = None
        timeout = runner_settings.RUNNER_SESSION_TIMEOUT_SECONDS

        with tempfile.TemporaryDirectory(prefix="learn_da_session_") as workdir:
            work = Path(workdir)
            try:
                prepare_workspace(work, request)
            except SessionWorkspaceError as exc:
                return build_result(
                    request_id=str(request.request_id),
                    execution_id=str(execution_id),
                    status=ExecutionStatus.REJECTED,
                    payload=None,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    error_type="invalid_session_request",
                    error_message=str(exc),
                )

            # The sandbox user (65532) must be able to read the mount.
            _relax_permissions(work)

            try:
                client = self._get_client()
                container = client.containers.run(
                    image=self._image,
                    command=["python", "-X", "utf8", "-B", DRIVER_FILENAME],
                    working_dir=_SESSION_MOUNT,
                    volumes={str(work): {"bind": _SESSION_MOUNT, "mode": "ro"}},
                    detach=True,
                    network_mode="none",
                    read_only=True,
                    user="65532:65532",
                    pids_limit=runner_settings.RUNNER_PIDS_LIMIT,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    mem_limit=f"{runner_settings.RUNNER_MEMORY_LIMIT_MB}m",
                    nano_cpus=runner_settings.RUNNER_CPU_QUOTA * 10_000,
                    tmpfs={"/tmp": f"size={runner_settings.RUNNER_TMPFS_SIZE_MB}m"},
                    auto_remove=False,
                )
                wait_result = container.wait(timeout=timeout)
                exit_code: int = wait_result.get("StatusCode", -1)
                raw_logs = container.logs(stdout=True, stderr=True)
                stdout_text, stderr_text = self._split_logs(raw_logs)
                duration_ms = int((time.monotonic() - start) * 1000)

                payload = parse_driver_output(stdout_text, MARKER)
                if payload is None:
                    return build_result(
                        request_id=str(request.request_id),
                        execution_id=str(execution_id),
                        status=ExecutionStatus.ERROR,
                        payload=None,
                        duration_ms=duration_ms,
                        error_type="driver_protocol_error",
                        error_message=(
                            f"driver exited with {exit_code}: "
                            f"{(stderr_text or stdout_text)[-800:]}"
                        ),
                    )
                return build_result(
                    request_id=str(request.request_id),
                    execution_id=str(execution_id),
                    status=ExecutionStatus.SUCCESS,
                    payload=payload,
                    duration_ms=duration_ms,
                    error_type=None if exit_code == 0 else "driver_nonzero_exit",
                )

            except Exception as exc:  # noqa: BLE001 - mirrors execute()
                duration_ms = int((time.monotonic() - start) * 1000)
                timed_out = "timeout" in str(exc).lower()
                if timed_out and container is not None:
                    try:
                        container.kill()
                    except Exception:
                        pass
                return build_result(
                    request_id=str(request.request_id),
                    execution_id=str(execution_id),
                    status=ExecutionStatus.TIMEOUT if timed_out else ExecutionStatus.ERROR,
                    payload=None,
                    duration_ms=duration_ms,
                    error_type="timeout" if timed_out else "execution_error",
                    error_message=str(exc)[:2000],
                )

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
