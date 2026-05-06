from functools import lru_cache
from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Learn DA Backend"
    APP_ENV: str = "development"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    API_PREFIX: str = "/api"
    API_VERSION: str = "v1"

    DATABASE_URL: str = "sqlite+aiosqlite:///./learn_da.db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    DB_POOL_PRE_PING: bool = True
    DB_ECHO: bool = False

    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,"
        "http://127.0.0.1:3000,http://127.0.0.1:5173"
    )
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_ALL_ORIGINS: bool = False

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_GLOBAL_IP: str = "200/minute"
    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_AGENT_CHAT: str = "20/minute"
    RATE_LIMIT_PLAYGROUND_EXECUTE: str = "10/minute"

    REDIS_ENABLED: bool = False
    REDIS_URL: Optional[str] = None
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_RETRY_ON_TIMEOUT: bool = True
    REDIS_HEALTH_CHECK_INTERVAL: int = 30
    REDIS_DEFAULT_EXPIRE: int = 300
    REDIS_SESSION_EXPIRE: int = 86400
    REDIS_CACHE_PREFIX: str = "learn-da"
    REDIS_CACHE_NULL_EXPIRE: int = 180

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_TURNS: int = 3
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: Optional[str] = None
    LEARN_DA_EMBEDDING_PROVIDER: str = "openai_compatible"
    LEARN_DA_EMBEDDING_API_KEY: Optional[str] = None
    LEARN_DA_EMBEDDING_BASE_URL: Optional[str] = None
    LEARN_DA_EMBEDDING_MODEL: Optional[str] = None
    LEARN_DA_EMBEDDING_DIM: Optional[int] = None
    VECTOR_STORE_TYPE: str = "in_memory"
    VECTOR_STORE_PATH: str = "knowledge_store.json"
    AGENT_ROUTING_STRATEGY: str = "hybrid"
    SESSION_STORE_TYPE: str = "in_memory"
    SESSION_STORE_PATH: str = "sessions"

    SANDBOX_DOCKER_ENABLED: bool = False
    SANDBOX_DOCKER_IMAGE: str = "polars-duckdb-sandbox:latest"
    SANDBOX_DOCKER_HOST: Optional[str] = None
    SANDBOX_TIMEOUT_SECONDS: int = 5
    SANDBOX_MEMORY_LIMIT_MB: int = 256
    SANDBOX_CPU_QUOTA: int = 50000
    SANDBOX_USE_MOCK_WHEN_DISABLED: bool = True
    SANDBOX_LOCAL_ENABLED: bool = True

    ENABLED_APP_MODULES: str = "learning,playground"

    MINIO_ENDPOINT: Optional[str] = None
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_KEY: Optional[str] = None
    BUCKET_NAME: str = "learn-da"
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    MAIL_FROM_NAME: Optional[str] = None
    MAIL_SERVER: Optional[str] = None
    MAIL_PORT: Optional[int] = None
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    USE_CREDENTIALS: bool = True
    EMAIL_VERIFICATION_EXPIRE: int = 300
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 1024 * 1024 * 1024
    ALLOWED_EXTENSIONS: list[str] = [
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".txt",
        ".md",
        ".csv",
        ".zip",
        ".rar",
        ".7z",
        ".tar",
        ".gz",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @property
    def enabled_app_modules(self) -> list[str]:
        return [
            module.strip()
            for module in self.ENABLED_APP_MODULES.split(",")
            if module.strip()
        ]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def effective_llm_api_key(self) -> Optional[str]:
        return self.LLM_API_KEY or self.OPENAI_API_KEY

    @property
    def effective_llm_base_url(self) -> Optional[str]:
        return self.LLM_BASE_URL or self.OPENAI_BASE_URL

    @property
    def effective_llm_model(self) -> str:
        return self.LLM_MODEL or self.OPENAI_MODEL

    @field_validator("API_PREFIX")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            return f"/{value}"
        return value.rstrip("/") or "/"

    @field_validator("API_VERSION")
    @classmethod
    def validate_api_version(cls, value: str) -> str:
        return value.strip("/").strip() or "v1"

    @field_validator("LEARN_DA_EMBEDDING_DIM", mode="before")
    @classmethod
    def empty_embedding_dim_as_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
