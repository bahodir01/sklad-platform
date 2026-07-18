"""Доступ к данным М1. Бизнес-правил здесь нет (архитектура §2).

Пять справочников имеют одинаковую форму доступа (список + деталь + вставка),
поэтому репозиторий один, параметризованный моделью. Пять копий одного кода
разошлись бы при первой же правке пагинации.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.shared.pagination import PageParams

M = TypeVar("M", bound=Base)


class CatalogRepository(Generic[M]):
    def __init__(self, session: AsyncSession, model: type[M]) -> None:
        self._session = session
        self._model = model

    async def get(self, entity_id: int) -> M | None:
        return await self._session.get(self._model, entity_id)

    async def list(
        self, params: PageParams, *, filters: list[Any] | None = None
    ) -> tuple[list[M], int]:
        stmt: Select[tuple[M]] = select(self._model)
        if filters:
            stmt = stmt.where(*filters)

        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self._session.scalars(
            stmt.order_by(self._model.id).offset(params.offset).limit(params.limit)
        )
        return list(rows), int(total or 0)

    def add(self, entity: M) -> M:
        self._session.add(entity)
        return entity
