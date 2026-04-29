# app/exceptions/base_exceptions.py
from typing import Optional, Any
from fastapi import HTTPException, status


class AppException(HTTPException):
    '''
    应用异常基类
    所有自定义异常的父类，提供统一的异常结构。
    属性:
        message: 错误消息
        status_code: HTTP状态码
        extra: 额外的错误信息（可选）
    '''
    def __init__(self, 
                 message: str, 
                 status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
                 extra: Optional[dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}
        super().__init__(status_code=status_code, detail=message)

    def tp_dict(self):
        return {
            "message": self.message,
            "status_code": self.status_code,
            **self.extra
        }

class BusinessException(AppException):
    """
    业务异常类

    用于处理业务逻辑中的异常情况，如：
    - 数据库操作失败
    - 权限不足
    - 资源不存在（如果业务上需要区分）
    - 其他业务规则违反

    默认状态码: 500

    示例:
        raise BusinessException("订单创建失败")
        raise BusinessException("余额不足", status_code=400, extra={"balance": 100, "required": 200})
    """

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        extra: Optional[dict[str, Any]] = None
    ):
        super().__init__(message, status_code, extra)


class ValidationException(AppException):
    """
    参数验证异常类

    用于处理请求参数验证失败的情况，如：
    - 必填参数缺失
    - 参数格式错误
    - 参数值超出范围
    - 业务验证失败（如用户名已存在）

    默认状态码: 400

    示例:
        raise ValidationException("用户名不能为空")
        raise ValidationException("用户名已存在", extra={"field": "username", "value": "admin"})
    """
    def __init__(self, 
                 message: str = "Validation failed",
                 status_code: int = status.HTTP_400_BAD_REQUEST,
                 extra: Optional[dict[str, Any]] = None):
        super().__init__(message, status_code, extra)
