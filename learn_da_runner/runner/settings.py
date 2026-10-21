"""Runner settings — separate from the API Settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RunnerSettings(BaseSettings):
    RUNNER_TOKEN: str = ""
    RUNNER_PORT: int = 8080
    # Execution backend. "docker" is the only isolated option; "local" runs the
    # snippet with a host interpreter and is development-only (see
    # runner/local_provider.py). Local mode additionally requires
    # RUNNER_ALLOW_LOCAL_EXECUTION=1 and is refused when RUNNER_ENV=production.
    RUNNER_PROVIDER: str = "docker"
    RUNNER_ALLOW_LOCAL_EXECUTION: bool = False
    RUNNER_LOCAL_PYTHON: str = ""  # empty = the interpreter running the Runner
    RUNNER_ENV: str = ""
    RUNNER_DOCKER_HOST: str | None = None  # None = local Docker socket
    RUNNER_DOCKER_IMAGE: str = "polars-duckdb-sandbox:latest"
    RUNNER_TIMEOUT_SECONDS: int = 5
    RUNNER_MEMORY_LIMIT_MB: int = 256
    RUNNER_CPU_QUOTA: int = 50_000  # Docker nano_cpus = quota * 10_000
    RUNNER_PIDS_LIMIT: int = 64
    RUNNER_TMPFS_SIZE_MB: int = 64
    RUNNER_MAX_OUTPUT_BYTES: int = 65_536  # 64 KiB per stream
    # Session execution replays every cell in one process, so the wall-clock
    # budget is much larger than a single snippet.
    RUNNER_SESSION_TIMEOUT_SECONDS: int = 20
    RUNNER_SESSION_MAX_DATASET_BYTES: int = 2_000_000  # 2 MB per request

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


runner_settings = RunnerSettings()
