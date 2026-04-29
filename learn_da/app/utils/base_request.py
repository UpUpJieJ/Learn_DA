"""
全局请求基类
提供统一的字段命名转换（驼峰 -> 下划线）
"""
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict, model_validator
import re

T = TypeVar('T')


def to_snake_case(string: str) -> str:
    """将驼峰命名转换为下划线命名"""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', string)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
    s3 = re.sub('([A-Z])([A-Z][a-z])', r'\1_\2', s2)
    return s3.lower()


class BaseRequestModel(BaseModel, Generic[T]):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    @model_validator(mode='before')
    @classmethod
    def convert_camel_to_snake(cls, data: Any) -> Any:
        """将前端传入的驼峰命名转换为下划线命名"""
        if not isinstance(data, dict):
            return data

        new_data = {}
        for key, value in data.items():
            new_key = to_snake_case(key)
            new_data[new_key] = value

        return new_data
