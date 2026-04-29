from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

from app.utils.base_response import BaseResponseModel


class UserResponse(BaseResponseModel):
    """用户响应数据"""
    id: int
    username: str
    email: str
    is_active: bool
    is_email_verified: bool
    email_verified_time: Optional[datetime] = None
    created_time: datetime
    updated_time: Optional[datetime] = None



class UserLoginResponse(BaseResponseModel):
    """用户登录响应数据"""
    access_token: str
    token_type: str
    user: UserResponse

    @classmethod
    def from_user_and_token(cls, orm_user, access_token: str, token_type: str = "Bearer"):
        """从用户和token创建登录响应"""
        user_info = UserResponse.model_validate(orm_user)
        return cls(
            access_token=access_token,
            token_type=token_type,
            user=user_info
        )

    
class Token(BaseModel):
    """swagger响应数据"""
    access_token: str
    token_type: str

