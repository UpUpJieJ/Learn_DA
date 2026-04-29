
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from config.settings import settings
from app.utils import log


class CORSSettings:

    def __init__(self):
        self.ALLOW_ORIGINS: List[str] = (
            [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
            if settings.CORS_ORIGINS
            else []
        )

        self.ALLOW_ALL_ORIGINS: bool = settings.CORS_ALLOW_ALL_ORIGINS

        self.ALLOW_METHODS: List[str] = [
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "PATCH",
            "OPTIONS",
            "HEAD"
        ]

        self.ALLOW_HEADERS: List[str] = [
            "*",  # 使用通配符时允许所有头部
            "Authorization",
            "Content-Type",
            "X-Requested-With",
            "X-API-Key",
            "Accept",
            "Origin",
        ]

        self.ALLOW_CREDENTIALS: bool = settings.CORS_ALLOW_CREDENTIALS

        self.EXPOSE_HEADERS: List[str] = [
            "X-Total-Count",
            "X-Page-Count",
        ]

        self.MAX_AGE: int = 600


def setup_cors_middleware(app) -> None:

    cors_settings = CORSSettings()

    origins_to_allow = ["*"] if cors_settings.ALLOW_ALL_ORIGINS else cors_settings.ALLOW_ORIGINS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins_to_allow,
        allow_credentials=cors_settings.ALLOW_CREDENTIALS,
        allow_methods=cors_settings.ALLOW_METHODS,
        allow_headers=cors_settings.ALLOW_HEADERS,
        expose_headers=cors_settings.EXPOSE_HEADERS,
        max_age=cors_settings.MAX_AGE,
    )

    log.info(f"CORS中间件已初始化，允许的源:\n {origins_to_allow}")
    log.debug(f"CORS设置 - 允许凭证: {cors_settings.ALLOW_CREDENTIALS}, "
              f"允许所有源: {cors_settings.ALLOW_ALL_ORIGINS}")

