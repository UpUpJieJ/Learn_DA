"""
速率限制配置模块

提供统一的速率限制配置和异常处理，确保：
1. RateLimitMiddleware（中间件级别）和 SlowAPI（装饰器级别）返回一致的响应格式
2. 异常消息统一且友好
3. 支持自定义限流规则，只需在一个地方配置
"""

from typing import Dict, Any, Optional, List
from fastapi import status
from app.utils.base_response import StdResp
from app.utils import log
import time
import re


class EndpointRateLimitRule:
    """端点限流规则
    
    每个端点可以配置自己的限流规则，包括：
    - 路径模式（支持正则表达式）
    - 错误消息
    - 默认重试时间
    """
    
    def __init__(
        self,
        name: str,
        path_patterns: List[str],
        error_message: str,
        default_retry_after: int = 60
    ):
        """
        初始化限流规则
        
        Args:
            name: 规则名称（端点类型）
            path_patterns: 路径模式列表（支持正则表达式）
            error_message: 错误消息
            default_retry_after: 默认重试时间（秒）
        """
        self.name = name
        self.path_patterns = path_patterns
        self.error_message = error_message
        self.default_retry_after = default_retry_after
        self._compiled_patterns = [re.compile(pattern) for pattern in path_patterns]
    
    def matches(self, path: str) -> bool:
        """
        检查路径是否匹配此规则
        
        Args:
            path: 请求路径
            
        Returns:
            bool: 是否匹配
        """
        return any(pattern.search(path) for pattern in self._compiled_patterns)


class RateLimitConfig:
    """速率限制配置类
    
    提供统一的限流配置和响应格式
    """
    
    # 默认规则（兜底）
    DEFAULT_RULE = EndpointRateLimitRule(
        name="default",
        path_patterns=[".*"],
        error_message="请求过于频繁，请稍后再试",
        default_retry_after=60
    )
    
    # 所有限流规则（按优先级排序，先匹配的优先）
    RULES: List[EndpointRateLimitRule] = [
        EndpointRateLimitRule(
            name="upload",
            path_patterns=[r"/upload", r".*upload.*"],
            error_message="上传请求过于频繁，请稍后再试",
            default_retry_after=60
        ),
        EndpointRateLimitRule(
            name="api",
            path_patterns=[r"/api/.*"],
            error_message="API调用过于频繁，请稍后再试",
            default_retry_after=60
        ),
    ]
    
    # HTTP 状态码
    RATE_LIMIT_STATUS_CODE = status.HTTP_429_TOO_MANY_REQUESTS
    
    @classmethod
    def add_rule(cls, rule: EndpointRateLimitRule, priority: int = -1):
        """
        添加新的限流规则
        
        Args:
            rule: 限流规则
            priority: 优先级（-1 表示添加到末尾，0 表示添加到开头）
        """
        if priority == 0:
            cls.RULES.insert(0, rule)
        elif priority == -1:
            cls.RULES.append(rule)
        else:
            cls.RULES.insert(priority, rule)
    
    @classmethod
    def get_rule_by_path(cls, path: str) -> EndpointRateLimitRule:
        """
        根据路径获取匹配的限流规则
        
        Args:
            path: 请求路径
            
        Returns:
            EndpointRateLimitRule: 匹配的规则（如果没有匹配则返回默认规则）
        """
        for rule in cls.RULES:
            if rule.matches(path):
                return rule
        return cls.DEFAULT_RULE
    
    @classmethod
    def get_rule_by_name(cls, name: str) -> Optional[EndpointRateLimitRule]:
        """
        根据名称获取限流规则
        
        Args:
            name: 规则名称
            
        Returns:
            Optional[EndpointRateLimitRule]: 规则对象（如果不存在则返回 None）
        """
        for rule in cls.RULES:
            if rule.name == name:
                return rule
        return None
    
    @classmethod
    def create_rate_limit_response(
        cls,
        message: Optional[str] = None,
        endpoint_type: str = "default",
        retry_after: Optional[int] = None,
        detail: Optional[str] = None
    ) -> StdResp:
        """
        创建统一的速率限制响应
        
        Args:
            message: 自定义错误消息（优先级高于 endpoint_type）
            endpoint_type: 端点类型
            retry_after: 重试时间（秒）
            detail: 详细信息
            
        Returns:
            StdResp: 统一格式的响应
        """
        # 获取规则
        rule = cls.get_rule_by_name(endpoint_type)
        if not rule:
            rule = cls.DEFAULT_RULE
        
        # 确定错误消息
        if message:
            error_msg = message
        else:
            error_msg = rule.error_message
        
        # 确定重试时间
        if retry_after is None:
            retry_after = rule.default_retry_after
        
        # 构建响应数据
        response_data: Dict[str, Any] = {
            "retryAfter": retry_after,
            "endpointType": endpoint_type
        }
        
        # 如果有详细信息，添加到响应中
        if detail:
            response_data["detail"] = detail
        
        return StdResp.error(
            msg=error_msg,
            code=cls.RATE_LIMIT_STATUS_CODE,
            data=response_data
        )


class RateLimitExceptionHandlers:
    """速率限制异常处理器集合
    
    提供统一的异常处理方法
    """
    
    @staticmethod
    async def handle_rate_limit_exceeded(request, exc) -> StdResp:
        """
        处理 SlowAPI 的 RateLimitExceeded 异常
        
        Args:
            request: FastAPI 请求对象
            exc: RateLimitExceeded 异常实例
            
        Returns:
            StdResp: 统一格式的响应
        """
        # 解析异常详情
        detail = str(exc.detail) if exc.detail else ""
        
        # 尝试从详情中提取重试时间
        retry_after = RateLimitConfig.DEFAULT_RULE.default_retry_after
        if detail:
            try:
                # SlowAPI 的错误格式通常是 "X per Y time"
                # 例如："10 per 1 minute"
                parts = detail.split()
                if len(parts) >= 4:
                    # 提取时间单位
                    time_unit = parts[3].lower()
                    if "second" in time_unit:
                        retry_after = 1
                    elif "minute" in time_unit:
                        retry_after = 60
                    elif "hour" in time_unit:
                        retry_after = 3600
                    elif "day" in time_unit:
                        retry_after = 86400
            except Exception as e:
                log.warning(f"解析限流异常详情失败: {e}")
        
        # 根据请求路径确定端点类型
        url = getattr(request, 'url', None)
        path = url.path if url is not None else ''
        rule = RateLimitConfig.get_rule_by_path(path)
        
        # 创建统一响应
        return RateLimitConfig.create_rate_limit_response(
            endpoint_type=rule.name,
            retry_after=retry_after,
            detail=detail
        )
    
    @staticmethod
    def handle_middleware_rate_limit(
        limit: int,
        remaining: int,
        reset: int,
        endpoint_type: str = "default"
    ) -> StdResp:
        """
        处理中间件级别的速率限制
        
        Args:
            limit: 限制数量
            remaining: 剩余数量
            reset: 重置时间戳
            endpoint_type: 端点类型
            
        Returns:
            StdResp: 统一格式的响应
        """
        return RateLimitConfig.create_rate_limit_response(
            endpoint_type=endpoint_type,
            retry_after=max(1, reset - int(__import__('time').time()))
        )


# 便捷函数，用于在路由中快速创建限流响应
def create_rate_limit_response(
    endpoint_type: str = "default",
    retry_after: int = 60,
    message: Optional[str] = None
) -> StdResp:
    """
    创建速率限制响应的便捷函数
    
    Args:
        endpoint_type: 端点类型
        retry_after: 重试时间（秒）
        message: 自定义错误消息
        
    Returns:
        StdResp: 限流响应
    """
    return RateLimitConfig.create_rate_limit_response(
        endpoint_type=endpoint_type,
        retry_after=retry_after,
        message=message
    )


# 装饰器：用于快速添加自定义限流规则
def register_rate_limit_rule(
    name: str,
    path_patterns: List[str],
    error_message: str,
    default_retry_after: int = 60,
    priority: int = -1
):
    """
    注册限流规则的装饰器
    
    使用示例：
    ```python
    @register_rate_limit_rule(
        name="custom",
        path_patterns=[r"/custom", r".*custom.*"],
        error_message="自定义请求过于频繁",
        default_retry_after=120
    )
    def some_function():
        pass
    ```
    
    Args:
        name: 规则名称
        path_patterns: 路径模式列表（支持正则表达式）
        error_message: 错误消息
        default_retry_after: 默认重试时间（秒）
        priority: 优先级（-1 表示添加到末尾，0 表示添加到开头）
    """
    def decorator(func):
        rule = EndpointRateLimitRule(
            name=name,
            path_patterns=path_patterns,
            error_message=error_message,
            default_retry_after=default_retry_after
        )
        RateLimitConfig.add_rule(rule, priority)
        return func
    return decorator
