"""Доступ к данным модуля auth. Бизнес-правил здесь нет (архитектура §2)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.scalar(select(User).where(User.id == user_id))

    async def get_by_username(self, username: str) -> User | None:
        return await self._session.scalar(select(User).where(User.username == username))

    async def exists_username(self, username: str) -> bool:
        result = await self._session.scalar(
            select(User.id).where(User.username == username).limit(1)
        )
        return result is not None

    def add(self, user: User) -> User:
        self._session.add(user)
        return user
