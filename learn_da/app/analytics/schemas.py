"""
阶段 1（重构）：学习行为事件采集 Pydantic Schema

事件类型收敛为枚举，新增幂等键和执行状态字段。
身份遵循阶段 0 签名匿名 session 约定，请求体不含 visitor_id。
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.utils.base_response import BaseResponseModel


class EventType(str, Enum):
    """学习事件类型枚举"""

    LESSON_START = "lesson_start"
    LESSON_COMPLETE = "lesson_complete"
    LESSON_UNCOMPLETE = "lesson_uncomplete"
    CODE_RUN = "code_run"
    CODE_SAVE = "code_save"
    AI_HELP = "ai_help"


class EventTrackRequest(BaseModel):
    """行为事件上报请求"""

    event_type: EventType = Field(..., alias="eventType", description="事件类型")
    lesson_slug: Optional[str] = Field(
        None, alias="lessonSlug", description="关联课程 slug"
    )
    duration_seconds: Optional[int] = Field(
        None, alias="durationSeconds", description="持续时长（秒）"
    )
    event_id: Optional[str] = Field(
        None, alias="eventId", description="幂等键（前端生成 UUID）"
    )
    status: Optional[str] = Field(
        None,
        description="执行结果: success / error / timeout / rejected（仅 code_run）",
    )


class EventTrackResponse(BaseResponseModel):
    """行为事件上报响应"""

    recorded: bool = True


class CodeSnapshotRequest(BaseModel):
    """代码快照保存请求"""

    lesson_slug: Optional[str] = Field(
        None, alias="lessonSlug", description="关联课程 slug"
    )
    code: str = Field(..., min_length=1, max_length=50000, description="代码内容")
    language: str = Field("python", description="代码语言")
    description: Optional[str] = Field(None, max_length=256, description="快照描述")


class CodeSnapshotResponse(BaseResponseModel):
    """代码快照保存响应"""

    snapshot_id: int
    version: int = 1


class CodeSnapshotItem(BaseResponseModel):
    """代码快照列表项"""

    id: int
    lesson_slug: Optional[str] = None
    code: str
    language: str
    version: int
    description: Optional[str] = None
    created_time: str


class CodeSnapshotPage(BaseResponseModel):
    """代码快照分页响应"""

    items: list[CodeSnapshotItem]
    total: int
    page: int
    page_size: int
