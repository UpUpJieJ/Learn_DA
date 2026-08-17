from functools import lru_cache
from typing import Any, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Learn DA Backend"
    APP_ENV: str = "development"
    # 对外访问协议（http/https）：决定会话 cookie 的 Secure 属性。
    # 默认 http（本地/明文 HTTP 部署）；启用 HTTPS 的环境显式设为 https。
    PUBLIC_SCHEME: str = "http"
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

    CORS_ORIGINS: str
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_ALL_ORIGINS: bool = False

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_GLOBAL_IP: str = "200/minute"
    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_AGENT_CHAT: str = "20/minute"
    RATE_LIMIT_PLAYGROUND_EXECUTE: str = "10/minute"
    RATE_LIMIT_ANALYTICS_WRITE: str = "30/minute"
    RATE_LIMIT_ANALYTICS_READ: str = "60/minute"

    # LLM_* 为主配置；FALLBACK_LLM_* 仅在对应主配置未设置时生效（effective_llm_* 统一解析）
    FALLBACK_LLM_API_KEY: Optional[str] = None
    FALLBACK_LLM_BASE_URL: Optional[str] = None
    FALLBACK_LLM_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_TURNS: int = 3
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: Optional[str] = None
    LLM_ENABLE_THINKING: bool = False
    LLM_TIMEOUT_SECONDS: float = 60
    LLM_MAX_RETRIES: int = 1
    # 阶段 ④：受限 Function Calling（只读工具 + 硬步数上限）。
    # 2026-07-28 FC 评测 90.2% ≥ 关键词基线 43.9%，默认开启；无 key 时仍确定性降级
    AGENT_FC_ENABLED: bool = True
    AGENT_FC_MAX_TOOL_ROUNDS: int = 2
    LEARN_DA_EMBEDDING_PROVIDER: str = "openai_compatible"
    LEARN_DA_EMBEDDING_API_KEY: Optional[str] = None
    LEARN_DA_EMBEDDING_BASE_URL: Optional[str] = None
    LEARN_DA_EMBEDDING_MODEL: Optional[str] = None
    LEARN_DA_EMBEDDING_DIM: Optional[int] = None

    RECOMMENDATION_CODE_RUNS_THRESHOLD: int = 5
    RECOMMENDATION_AI_HELPS_THRESHOLD: int = 3
    RECOMMENDATION_REVIEW_COOLDOWN_SECONDS: int = 86400
    RECOMMENDATION_RESUME_ABSENCE_THRESHOLD_DAYS: int = 3

    RUNNER_URL: str = "http://127.0.0.1:8080"
    RUNNER_TOKEN: str = ""
    RUNNER_TIMEOUT_SECONDS: float = 7.0
    SESSION_SECRET: str = "development-only-change-me"
    SESSION_COOKIE_NAME: str = "learn_da_session"
    SNAPSHOT_MAX_PER_SESSION: int = 100
    SNAPSHOT_MAX_GLOBAL: int = 10_000
    SNAPSHOT_PAGE_SIZE_DEFAULT: int = 20
    SNAPSHOT_PAGE_SIZE_MAX: int = 50
    TRUSTED_PROXY_IPS: str = ""
    OPENAPI_ENABLED: bool = False

    ENABLED_APP_MODULES: str = "learning,playground,agent,analytics,learner_state,practice"

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
        return self.LLM_API_KEY or self.FALLBACK_LLM_API_KEY

    @property
    def effective_llm_base_url(self) -> Optional[str]:
        return self.LLM_BASE_URL or self.FALLBACK_LLM_BASE_URL

    @property
    def effective_llm_model(self) -> str:
        return self.LLM_MODEL or self.FALLBACK_LLM_MODEL

    @field_validator("PUBLIC_SCHEME")
    @classmethod
    def validate_public_scheme(cls, value: str) -> str:
        scheme = value.strip().lower()
        if scheme not in ("http", "https"):
            raise ValueError("PUBLIC_SCHEME must be 'http' or 'https'")
        return scheme

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

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.APP_ENV != "production":
            return self
        if not self.RUNNER_URL.strip():
            raise ValueError("RUNNER_URL is required in production")
        if len(self.RUNNER_TOKEN) < 32:
            raise ValueError(
                "RUNNER_TOKEN must contain at least 32 characters")
        if len(self.SESSION_SECRET) < 32:
            raise ValueError(
                "SESSION_SECRET must contain at least 32 characters")
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
