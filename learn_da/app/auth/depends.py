from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repository import AuthRepository
from app.auth.service import AuthService
from app.core import get_db
from app.core.redis import AsyncRedisClient
from ..utils.security import get_current_user


def get_async_redis_client() -> AsyncRedisClient:
    return AsyncRedisClient()


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    redis_client: AsyncRedisClient = Depends(get_async_redis_client),
) -> AuthService:
    """
    通过 router 的 Depends 注入数据库 session，由 service 负责管理并组装 repository。
    每个请求都会获得独立的 AsyncSession。
    """
    auth_repo = AuthRepository()
    return AuthService(db=db, auth_repository=auth_repo, redis_client=redis_client)


get_current_user = get_current_user

