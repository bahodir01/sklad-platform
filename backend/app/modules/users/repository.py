"""Доступ к данным М7 «Пользователи». Бизнес-правил здесь нет (архитектура §2).

Не реиспользует auth/repository.UserRepository: тот обслуживает вход
(поиск по логину), здесь — админский CRUD со списком/фильтрами по образцу
catalog/repository. Модель одна и та же — modules/auth/models.User,
дублирования модели нет.
"""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.shared.pagination import PageParams


class UsersCrudRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def list(
        self, params: PageParams, *, filters: list[Any] | None = None
    ) -> tuple[list[User], int]:
        stmt: Select[tuple[User]] = select(User)
        if filters:
            stmt = stmt.where(*filters)

        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.scalars(
            stmt.order_by(User.id).offset(params.offset).limit(params.limit)
        )
        return list(rows), int(total or 0)

    async def username_taken(self, username: str) -> bool:
        row = await self._session.scalar(
            select(User.id).where(User.username == username).limit(1)
        )
        return row is not None

    async def email_taken(self, email: str, *, exclude_id: int | None = None) -> bool:
        stmt = select(User.id).where(User.email == email)
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        row = await self._session.scalar(stmt.limit(1))
        return row is not None

    def add(self, user: User) -> User:
        self._session.add(user)
        return user
