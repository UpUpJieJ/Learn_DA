from datetime import datetime, timedelta
import hashlib
import secrets
import ujson
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings

from .exceptions import (
    EmailExistedException,
    InactiveUserException,
    InvalidCredentialsException,
    InvalidOrExpiredTokenException,
    UserExistedException,
    UserNotFoundException,
)
from .models import User
from .repository import AuthRepository
from .schemas import UserCreate, UserLogin, UserUpdate
from .schemas_res import UserLoginResponse, UserResponse
from ..core import AsyncSessionLocal
from ..core.redis import AsyncRedisClient
from ..utils.pagination import PaginationResult, create_pagination_result
from ..utils.security import get_password_hash, jwt_security_service, verify_password


ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
user_detail_key = "user_detail:"


class AuthService:
    """
    Service 持有当前请求的 AsyncSession，负责任务边界内的事务提交/刷新，
    Repository 只负责构造和执行 SQL。
    """

    def __init__(
        self,
        db: AsyncSession,
        auth_repository: AuthRepository,
        redis_client: AsyncRedisClient = None,
    ):
        self.db = db
        self.auth_repository = auth_repository
        self.redis_client = redis_client

    async def create_user(self, user: UserCreate, base_url: str = ""):
        existing_user = await self.auth_repository.get_user_by_username(self.db, user.username)
        if existing_user:
            raise UserExistedException()

        existing_email = await self.auth_repository.get_user_by_email(self.db, user.email)
        if existing_email:
            raise EmailExistedException()

        hashed_password = get_password_hash(user.password)
        db_user = User(
            username=user.username,
            email=user.email,
            hashed_password=hashed_password,
        )
        await self.auth_repository.create_user(self.db, db_user)
        await self.db.commit()
        await self.db.refresh(db_user)

        # 如需使用 created_user，可在此返回或继续后续逻辑
        # 发送验证邮件逻辑省略
        return None

    async def authenticate_user(self, user_login: UserLogin) -> User:
        user = await self.auth_repository.get_user_by_username(self.db, user_login.username)

        if not user or not verify_password(user_login.password, user.hashed_password):
            raise InvalidCredentialsException()

        if not user.is_active:
            raise InactiveUserException()

        return user

    def _token_hash(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _email_verify_key(self, token: str) -> str:
        return f"{settings.REDIS_CACHE_PREFIX}:email_verify:{self._token_hash(token)}"

    async def create_email_verification_token(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        key = self._email_verify_key(token)
        ok = await self.redis_client.set(key, str(user_id), expire=settings.EMAIL_VERIFICATION_EXPIRE)
        if not ok:
            raise InvalidOrExpiredTokenException(message="无法创建邮箱验证 Token")
        return token

    async def verify_email_token(self, token: str) -> UserResponse:
        key = self._email_verify_key(token)
        user_id = await self.redis_client.get(key)
        if not user_id:
            raise InvalidOrExpiredTokenException()

        await self.redis_client.delete(key)
        affected = await self.auth_repository.update_user(
            self.db,
            int(user_id),
            {
                "is_email_verified": True,
                "email_verified_time": datetime.now(ZoneInfo("Asia/Shanghai")),
            },
        )
        if not affected:
            raise InvalidOrExpiredTokenException(message="用户不存在")

        await self.db.commit()
        user = await self.auth_repository.get_user_by_id(self.db, int(user_id))
        return UserResponse.model_validate(user)

    async def login_user(self, user_login: UserLogin) -> UserLoginResponse:
        user = await self.authenticate_user(user_login)
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = jwt_security_service.create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        return UserLoginResponse.from_user_and_token(
            orm_user=user,
            access_token=access_token,
        )

    async def get_user_by_id(self, user_id: int) -> Optional[UserResponse]:
        """获取用户信息（通过 Redis 逻辑过期缓存）"""
        key = user_detail_key + str(user_id)

        async def query_user(user_id: int, session: AsyncSession):
            repo = AuthRepository()
            return await repo.get_user_by_id(session, user_id)

        return await self.redis_client.query_with_logical_expire_cache(
            key,
            user_id,
            UserResponse,
            query_user,
            20,
            session_factory=AsyncSessionLocal,
        )

    async def get_all_users(self, page: int = 1, size: int = 10) -> PaginationResult[UserResponse]:
        users, total = await self.auth_repository.get_users_paginated(self.db, page, size)
        user_responses = [UserResponse.model_validate(user) for user in users]
        return create_pagination_result(
            items=user_responses,
            total=total,
            page=page,
            page_size=size,
        )

    async def update_user(self, user_id: int, update_data: dict) -> Optional[UserResponse]:
        affected = await self.auth_repository.update_user(self.db, user_id, update_data)
        if not affected:
            await self.db.rollback()
            return None
        await self.db.commit()
        user = await self.auth_repository.get_user_by_id(self.db, user_id)
        return UserResponse.model_validate(user)

    async def delete_user(self, user_id: int) -> bool:
        """删除用户"""
        affected = await self.auth_repository.delete_user(self.db, user_id)
        if not affected:
            await self.db.rollback()
            return False
        await self.db.commit()
        return True

    async def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        user = await self.auth_repository.get_user_by_id(self.db, user_id)
        if not user or not verify_password(old_password, user.hashed_password):
            raise InvalidCredentialsException()

        update_data = {"hashed_password": get_password_hash(new_password)}
        affected = await self.auth_repository.update_user(self.db, user_id, update_data)
        if not affected:
            await self.db.rollback()
            return False
        await self.db.commit()
        return True

    async def update_user_info(self, user_id: int, update_data: UserUpdate) -> UserResponse:
        user = await self.auth_repository.get_user_by_id(self.db, user_id)
        if not user:
            raise InvalidCredentialsException(message="User not found")

        data_to_update = {}
        if update_data.email is not None:
            existing_user = await self.auth_repository.get_user_by_email(self.db, update_data.email)
            if existing_user and existing_user.id != user_id:
                raise EmailExistedException()
            data_to_update["email"] = update_data.email
            data_to_update["is_email_verified"] = False
            data_to_update["email_verified_time"] = None

        if update_data.password is not None:
            data_to_update["hashed_password"] = get_password_hash(update_data.password)

        if data_to_update:
            affected = await self.auth_repository.update_user(self.db, user_id, data_to_update)
            if not affected:
                await self.db.rollback()
                raise InvalidCredentialsException(message="Failed to update user")
            await self.db.commit()
            updated_user = await self.auth_repository.get_user_by_id(self.db, user_id)
            return UserResponse.model_validate(updated_user)

        return UserResponse.model_validate(user)
