"""
app 包：项目核心入口
对外暴露核心路由、数据库依赖、配置等，简化外部导入
"""

from .core import get_db

__all__ = [
    "get_db",
]
