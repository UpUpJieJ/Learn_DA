"""Local subprocess execution provider — development only.

The Docker provider is the only execution boundary that isolates learner code
from the host. This provider exists so the product loop can be exercised on a
machine without Docker (or without WSL2/Hyper-V): it runs the snippet in a
short-lived child process with the same timeout and output caps, but it is
**not** a security boundary — no network isolation, no read-only filesystem,
no privilege drop.

It is therefore gated twice: ``RUNNER_PROVIDER=local`` must be set *and*
``RUNNER_ALLOW_LOCAL_EXECUTION=1``, and the runner refuses to start with it
when ``RUNNER_ENV=production`` (or ``APP_ENV=production``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

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


def _clip_bytes(raw: bytes, limit: int) -> tuple[str, bool]:
    if len(raw) <= limit:
        return raw.decode("utf-8", errors="replace"), False
    return raw[:limit].decode("utf-8", errors="replace"), True


class LocalSubprocessProvider:
    """Run the snippet with a host interpreter (development only)."""

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self._python = python_executable or (
            runner_settings.RUNNER_LOCAL_PYTHON or sys.executable)
        self._timeout = (
            runner_settings.RUNNER_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )

    # ------------------------------------------------------------------
    # Protocol
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        try:
            completed = subprocess.run(
                [self._python, "-I", "-B", "-c", "print(1)"],
                capture_output=True,
                timeout=10,
                env=self._child_env(),
            )
            return completed.returncode == 0
        except Exception:
            return False

    def execute(self, request: RunnerExecutionRequest) -> dict:
        execution_id = uuid4()
        start = time.monotonic()
        proc: subprocess.Popen | None = None

        with tempfile.TemporaryDirectory(prefix="learn_da_local_") as workdir:
            work = Path(workdir)
            out_path = work / "_stdout"
            err_path = work / "_stderr"

            try:
                with out_path.open("wb") as out_file, err_path.open("wb") as err_file:
                    proc = subprocess.Popen(
                        # -X utf8 is a command-line flag, so it survives -I
                        # (isolated mode ignores PYTHON* environment variables).
                        # Without it the child writes the Windows locale codec
                        # (cp936 here) and Chinese output decodes as mojibake.
                        [self._python, "-I", "-X", "utf8", "-B", "-c", request.code],
                        cwd=workdir,
                        stdin=subprocess.DEVNULL,
                        stdout=out_file,
                        stderr=err_file,
                        env=self._child_env(),
                    )
                    exit_code = proc.wait(timeout=self._timeout)

                duration_ms = int((time.monotonic() - start) * 1000)
                stdout_text, stdout_clipped = self._read_capped(out_path)
                stderr_text, stderr_clipped = self._read_capped(err_path)

                if exit_code == 0:
                    status_value = ExecutionStatus.SUCCESS
                    error_type = None
                else:
                    status_value = ExecutionStatus.ERROR
                    error_type = "runtime_error"

                return {
                    "requestId": str(request.request_id),
                    "executionId": str(execution_id),
                    "status": status_value,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "errorType": error_type,
                    "durationMs": duration_ms,
                    "outputTruncated": stdout_clipped or stderr_clipped,
                }

            except subprocess.TimeoutExpired:
                if proc is not None:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                duration_ms = int((time.monotonic() - start) * 1000)
                stdout_text, stdout_clipped = self._read_capped(out_path)
                stderr_text, stderr_clipped = self._read_capped(err_path)
                return {
                    "requestId": str(request.request_id),
                    "executionId": str(execution_id),
                    "status": ExecutionStatus.TIMEOUT,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "errorType": "timeout",
                    "durationMs": duration_ms,
                    "outputTruncated": stdout_clipped or stderr_clipped,
                }

            except Exception as exc:  # pragma: no cover - defensive
                if proc is not None and proc.poll() is None:
                    proc.kill()
                duration_ms = int((time.monotonic() - start) * 1000)
                return {
                    "requestId": str(request.request_id),
                    "executionId": str(execution_id),
                    "status": ExecutionStatus.ERROR,
                    "stdout": "",
                    "stderr": str(exc)[:2000],
                    "errorType": "execution_error",
                    "durationMs": duration_ms,
                    "outputTruncated": False,
                }

    # ------------------------------------------------------------------
    # Session execution (replay-style)
    # ------------------------------------------------------------------

    def execute_session(self, request: RunnerSessionRequest) -> dict:
        """Replay every cell in one short-lived process, then check assertions."""
        execution_id = uuid4()
        start = time.monotonic()
        proc: subprocess.Popen | None = None
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

            out_path = work / "_stdout"
            err_path = work / "_stderr"
            try:
                with out_path.open("wb") as out_file, err_path.open("wb") as err_file:
                    proc = subprocess.Popen(
                        [self._python, "-I", "-X", "utf8", "-B", DRIVER_FILENAME],
                        cwd=workdir,
                        stdin=subprocess.DEVNULL,
                        stdout=out_file,
                        stderr=err_file,
                        env=self._child_env(),
                    )
                    exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if proc is not None:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                return build_result(
                    request_id=str(request.request_id),
                    execution_id=str(execution_id),
                    status=ExecutionStatus.TIMEOUT,
                    payload=None,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    error_type="timeout",
                    error_message=f"session exceeded {timeout}s",
                )
            except Exception as exc:  # pragma: no cover - defensive
                if proc is not None and proc.poll() is None:
                    proc.kill()
                return build_result(
                    request_id=str(request.request_id),
                    execution_id=str(execution_id),
                    status=ExecutionStatus.ERROR,
                    payload=None,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    error_type="execution_error",
                    error_message=str(exc)[:2000],
                )

            duration_ms = int((time.monotonic() - start) * 1000)
            stdout_text, _ = self._read_capped(out_path)
            stderr_text, _ = self._read_capped(err_path)
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _child_env() -> dict[str, str]:
        """Minimal environment: keep the OS bits Python needs, drop the rest."""
        keep = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATH", "TEMP", "TMP",
                "HOME", "USERPROFILE", "LANG")
        env = {key: os.environ[key] for key in keep if key in os.environ}
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    @staticmethod
    def _read_capped(path: Path) -> tuple[str, bool]:
        try:
            raw = path.read_bytes()
        except OSError:
            return "", False
        text, clipped = _clip_bytes(raw, runner_settings.RUNNER_MAX_OUTPUT_BYTES)
        # Windows text streams emit CRLF; the Docker sandbox is Linux and emits
        # LF. Normalise so exercise expectations behave the same in both.
        return text.replace("\r\n", "\n"), clipped