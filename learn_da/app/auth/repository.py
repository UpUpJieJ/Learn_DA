from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User


class AuthRepository:
    """
    只负责构造和执行 SQL，不持有 Session，也不负责提交事务。
    """

    async def get_user_by_id(self, db: AsyncSession, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_username(self, db: AsyncSession, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create_user(self, db: AsyncSession, user: User) -> User:
        """创建用户（不提交事务）"""
        db.add(user)
        return user

    async def get_all_users(self, db: AsyncSession) -> List[User]:
        """获取所有用户"""
        result = await db.execute(select(User).order_by(User.created_at))
        return result.scalars().all()

    async def get_users_paginated(self, db: AsyncSession, page: int, size: int) -> Tuple[List[User], int]:
        """分页获取用户列表"""
        offset = (page - 1) * size

        stmt = select(User).order_by(User.created_time).offset(offset).limit(size)
        result = await db.execute(stmt)
        users = result.scalars().all()

        count_stmt = select(func.count()).select_from(User)
        count_result = await db.execute(count_stmt)
        total = count_result.scalar_one()

        return users, total

    async def update_user(self, db: AsyncSession, user_id: int, update_data: Dict[str, Any]) -> int:
        """更新用户信息，返回受影响行数（不提交事务）"""
        stmt = update(User).where(User.id == user_id).values(**update_data)
        result = await db.execute(stmt)
        return result.rowcount or 0

    async def delete_user(self, db: AsyncSession, user_id: int) -> int:
        """删除用户，返回受影响行数（不提交事务）"""
        stmt = delete(User).where(User.id == user_id)
        result = await db.execute(stmt)
        return result.rowcount or 0
