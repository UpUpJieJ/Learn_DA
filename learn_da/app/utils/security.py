"""
统一安全模块

提供以下功能：
1. 密码加密和验证
2. JWT 令牌的创建、验证和用户认证
3. HTML 转义（防止 XSS 攻击）
"""

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from pydantic import BaseModel
import html

from config.settings import settings
from app.auth.schemas_res import UserResponse
from app.core import get_db
from app.auth.exceptions import TokenValidationException
from app.utils.base_response import StdResp
from app.core.redis import AsyncRedisClient


# =================================================================
# 密码加密配置
# =================================================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码
    
    Args:
        plain_password: 明文密码
        hashed_password: 哈希密码
        
    Returns:
        bool: 密码是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    获取密码哈希
    
    Args:
        password: 明文密码
        
    Returns:
        str: 哈希后的密码
    """
    return pwd_context.hash(password)



SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class JWTSecurityService:
    """JWT安全服务类"""

    def __init__(self):
        self.secret_key = SECRET_KEY
        self.algorithm = ALGORITHM
        self.access_token_expire_minutes = ACCESS_TOKEN_EXPIRE_MINUTES
        self.redis_client = AsyncRedisClient()

    def _get_token_blacklist_key(self, token: str) -> str:
        """获取 token 黑名单的 Redis key"""
        return f"{settings.REDIS_CACHE_PREFIX}:token_blacklist:{token}"

    async def add_token_to_blacklist(self, token: str) -> bool:
        """
        将 token 添加到黑名单

        Args:
            token: JWT token

        Returns:
            bool: 是否添加成功
        """
        key = self._get_token_blacklist_key(token)
        # 设置过期时间为 token 的剩余有效时间
        expire_seconds = self.access_token_expire_minutes * 60
        return await self.redis_client.set(key, "1", expire=expire_seconds)

    async def is_token_blacklisted(self, token: str) -> bool:
        """
        检查 token 是否在黑名单中

        Args:
            token: JWT token

        Returns:
            bool: 是否在黑名单中
        """
        key = self._get_token_blacklist_key(token)
        return await self.redis_client.exists(key)

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """
        创建访问令牌
        
        Args:
            data: 要编码的数据
            expires_delta: 自定义过期时间
            
        Returns:
            str: JWT token
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(ZoneInfo("Asia/Shanghai")) + expires_delta
        else:
            expire = datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> str:
        """
        验证令牌
        
        Args:
            token: JWT token
            
        Returns:
            str: 用户名
            
        Raises:
            TokenValidationException: 当 token 无效或过期时
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            username: str = payload.get("sub")
            if username is None:
                raise TokenValidationException(message="Token 无效")
            return username
        except JWTError as e:
            raise TokenValidationException(message=f"Token 验证失败: {str(e)}")

    async def get_current_user(
        self,
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db)
    ) -> UserResponse:
        # 检查 token 是否在黑名单中
        if await self.is_token_blacklisted(token):
            raise TokenValidationException(
                message="Token 已失效，请重新登录",
            )

        # 验证 token 并获取用户名
        username = self.verify_token(token)

        # 延迟导入以避免循环导入
        from app.auth.repository import AuthRepository
        
        # 获取用户仓库
        auth_repository = AuthRepository(db)
        user = await auth_repository.get_user_by_username(username)

        if user is None:
            raise TokenValidationException(message="用户不存在")

        # 返回用户响应模型
        return UserResponse.model_validate(user)


jwt_security_service = JWTSecurityService()

async def get_token_dependency(token: str = Depends(oauth2_scheme)) -> str:
    return token


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    return await jwt_security_service.get_current_user(token, db)




def escape_recursive(value):
    if isinstance(value, str):
        return html.escape(value)
    elif isinstance(value, list):
        return [escape_recursive(item) for item in value]
    elif isinstance(value, dict):
        return {k: escape_recursive(v) for k, v in value.items()}
    elif isinstance(value, BaseModel):
        for field_name, field_value in value.model_dump().items():
            setattr(value, field_name, escape_recursive(field_value))
        return value
    else:
        return value


class SafeBaseModel(BaseModel):
    def __init__(self, **data):
        cleaned_data = {k: escape_recursive(v) for k, v in data.items()}
        super().__init__(**cleaned_data)
