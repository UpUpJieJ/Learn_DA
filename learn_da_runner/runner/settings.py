"""Runner settings — separate from the API Settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RunnerSettings(BaseSettings):
    RUNNER_TOKEN: str = ""
    RUNNER_PORT: int = 8080
    RUNNER_DOCKER_HOST: str | None = None  # None = local Docker socket
    RUNNER_DOCKER_IMAGE: str = "polars-duckdb-sandbox:latest"
    RUNNER_TIMEOUT_SECONDS: int = 5
    RUNNER_MEMORY_LIMIT_MB: int = 256
    RUNNER_CPU_QUOTA: int = 50_000  # Docker nano_cpus = quota * 10_000
    RUNNER_PIDS_LIMIT: int = 64
    RUNNER_TMPFS_SIZE_MB: int = 64
    RUNNER_MAX_OUTPUT_BYTES: int = 65_536  # 64 KiB per stream

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


runner_settings = RunnerSettings()
