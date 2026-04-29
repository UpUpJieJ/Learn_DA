from app.core.exceptions.base_exceptions import AppException


class UserExistedException(AppException):
    def __init__(self, message: str = "用户名已存在", status_code: int = 400):
        super().__init__(message=message, status_code=status_code)


class EmailExistedException(AppException):
    def __init__(self, message: str = "邮箱已注册", status_code: int = 400):
        super().__init__(message=message, status_code=status_code)


class InvalidCredentialsException(AppException):
    def __init__(self, message: str = "用户名或密码错误", status_code: int = 401):
        super().__init__(message=message, status_code=status_code)


class InactiveUserException(AppException):
    def __init__(self, message: str = "用户未激活", status_code: int = 400):
        super().__init__(message=message, status_code=status_code)


class TokenValidationException(AppException):
    def __init__(self, message: str = "无法验证凭据", status_code: int = 401):
        super().__init__(message=message, status_code=status_code)


class EmailNotVerifiedException(AppException):
    def __init__(self, message: str = "邮箱未验证", status_code: int = 403):
        super().__init__(message=message, status_code=status_code)


class InvalidOrExpiredTokenException(AppException):
    def __init__(self, message: str = "Token无效或已过期", status_code: int = 400):
        super().__init__(message=message, status_code=status_code)

class UserNotFoundException(AppException):
    def __init__(self, message: str = "用户不存在", status_code: int = 404):
        super().__init__(message=message, status_code=status_code)