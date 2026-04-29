from pydantic import BaseModel, EmailStr, field_validator, model_validator
from datetime import datetime
from typing import Optional

from app.utils.base_request import BaseRequestModel


class UserBase(BaseRequestModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    """用户注册"""
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str):
        if len(v) < 6:
            raise ValueError("Password too short")
        return v


class UserLogin(BaseRequestModel):
    """用户登录"""
    username: str
    password: str


class EmailVerificationRequest(BaseRequestModel):
    token: str


class UserUpdate(BaseRequestModel):
    """用户信息更新请求模型
    - username 字段不可修改
    - email 修改后会重置验证状态
    - password 修改需要满足复杂度要求
    """
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    
    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        """确保至少提供一个要更新的字段"""
        if not self.email and not self.password:
            raise ValueError("At least one field (email or password) must be provided")
        return self
    
    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: Optional[str]) -> Optional[str]:
        """验证密码复杂度"""
        if v is not None:
            if len(v) < 8:
                raise ValueError("Password must be at least 8 characters long")
            if not any(c.isupper() for c in v):
                raise ValueError("Password must contain at least one uppercase letter")
            if not any(c.islower() for c in v):
                raise ValueError("Password must contain at least one lowercase letter")
            if not any(c.isdigit() for c in v):
                raise ValueError("Password must contain at least one digit")
        return v
