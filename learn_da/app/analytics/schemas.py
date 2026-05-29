"""
Phase 2: 学习行为事件采集 Pydantic Schema
"""

from typing import Optional

from pydantic import BaseModel, Field

from app.utils.base_response import BaseResponseModel


class EventTrackRequest(BaseModel):
    """行为事件上报请求"""
    visitor_id: str = Field(..., alias="visitorId", description="访客 ID")
    event_type: str = Field(..., alias="eventType", description="事件类型")
    lesson_slug: Optional[str] = Field(None, alias="lessonSlug", description="关联课程 slug")
    duration_seconds: Optional[int] = Field(None, alias="durationSeconds", description="持续时长（秒）")


class EventTrackResponse(BaseResponseModel):
    """行为事件上报响应"""
    recorded: bool = True


class CodeSnapshotRequest(BaseModel):
    """代码快照保存请求"""
    visitor_id: str = Field(..., alias="visitorId", description="访客 ID")
    lesson_slug: Optional[str] = Field(None, alias="lessonSlug", description="关联课程 slug")
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
