"""
全局响应基类
提供统一的字段命名转换（下划线 -> 驼峰）
"""
from typing import Any, Generic, TypeVar, Self
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from fastapi.responses import JSONResponse
from datetime import datetime
T = TypeVar('T')


def to_camel_case(string: str) -> str:
    return to_camel(string)


class BaseResponseModel(BaseModel, Generic[T]):
    """全局响应基类"""
    
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel_case,
        use_enum_values=True,
        json_encoders={
            # 可以在这里添加自定义的JSON序列化器
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S")
        }
    )


class StdResp(BaseModel, Generic[T]):
    """标准响应模型
    
    所有API响应都应使用此格式，确保响应格式的一致性
    
    字段会自动转换为驼峰命名:
    - data: 响应数据
    - code: HTTP状态码
    - msg: 响应消息
    
    Attributes:
        data: 响应数据，成功时返回具体数据，失败时可为None
        code: HTTP状态码，用于表示请求的处理结果
        msg: 响应消息，用于描述处理结果
    """
    data: T | None = None
    code: int = 200
    msg: str = "success"
    
    model_config = ConfigDict(
        alias_generator=to_camel_case,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "data": {"userId": 1, "userName": "示例数据"},
                "code": 200,
                "msg": "success"
            }
        }
    )

    def to_response(self) -> JSONResponse:
        """转换为 JSONResponse
        
        Returns:
            JSONResponse: FastAPI的响应对象
        """
        return JSONResponse(
            content=self.model_dump(by_alias=True),
            status_code=self.code
        )

    @classmethod
    def success(cls, data: T = None, msg: str = "success", code: int = 200) -> "StdResp[T]":
        """创建成功响应

        Args:
            data: 响应数据
            msg: 成功消息，默认为"success"
            code: HTTP状态码，默认为200

        Returns:
            StdResp: 成功响应对象
        """
        return cls(data=data, msg=msg, code=code)

    @classmethod
    def error(cls, msg: str, code: int = 400, data: Any = None) -> "StdResp[Any]":
        """创建错误响应

        Args:
            msg: 错误消息
            code: HTTP状态码，默认为400
            data: 错误相关的额外数据

        Returns:
            StdResp: 错误响应对象
        """
        return cls(data=data, msg=msg, code=code)

    @classmethod
    def not_found(cls, msg: str = "Not Found", data: Any = None) -> "StdResp[Any]":
        """创建404响应

        Args:
            msg: 404错误消息，默认为"Not Found"
            data: 错误相关的额外数据

        Returns:
            StdResp: 404响应对象
        """
        return cls(data=data, msg=msg, code=404)

    @classmethod
    def unauthorized(cls, msg: str = "Unauthorized", data: Any = None) -> "StdResp[Any]":
        """创建401响应

        Args:
            msg: 未授权消息，默认为"Unauthorized"
            data: 错误相关的额外数据

        Returns:
            StdResp: 401响应对象
        """
        return cls(data=data, msg=msg, code=401)

    @classmethod
    def forbidden(cls, msg: str = "Forbidden", data: Any = None) -> "StdResp[Any]":
        """创建403响应

        Args:
            msg: 禁止访问消息，默认为"Forbidden"
            data: 错误相关的额外数据

        Returns:
            StdResp: 403响应对象
        """
        return cls(data=data, msg=msg, code=403)

    @classmethod
    def server_error(cls, msg: str = "Internal Server Error", data: Any = None) -> "StdResp[Any]":
        """创建500响应

        Args:
            msg: 服务器错误消息，默认为"Internal Server Error"
            data: 错误相关的额外数据

        Returns:
            StdResp: 500响应对象
        """
        return cls(data=data, msg=msg, code=500)
