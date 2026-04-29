from pydantic import ConfigDict
from sqlalchemy import Column, Integer, DateTime, func, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class BaseModel(Base):
    __abstract__ = True
    id = Column(Integer, primary_key=True, index=True, comment="主键")
    created_time = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_time = Column(DateTime(timezone=True), onupdate=func.now(), comment="更新时间")
    is_deleted = Column(Boolean, default=False, comment="逻辑删除")

