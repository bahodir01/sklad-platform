"""Доступ к данным М5 (архитектура §2 — без бизнес-правил).

Балансы касс (AP-9) и «мои расходы» сотрудника (row-level в сервисе, §1.3).
Блокировку строки кассы (FOR UPDATE) берёт СЕРВИС, а не репозиторий: она —
часть бизнес-инварианта «не уйти в минус», а не деталь чтения.
"""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cash.models import CashDesk, MoneyExpense
from app.shared.pagination import PageParams


class CashRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_desks(self) -> list[CashDesk]:
        """Обе кассы, стабильный порядок по id (teacher=1, worker=2)."""
        rows = await self._session.scalars(select(CashDesk).order_by(CashDesk.id))
        return list(rows)

    async def list_expenses(
        self, params: PageParams, *, filters: list[Any] | None = None
    ) -> tuple[list[MoneyExpense], int]:
        """Список расходов — offset-пагинация, сортировка (date DESC, id DESC).

        Ложится на composite-индексы AP-8 (employee_id, date DESC) —
        «мои расходы» сотрудника читаются точечно.
        """
        stmt: Select[tuple[MoneyExpense]] = select(MoneyExpense)
        if filters:
            stmt = stmt.where(*filters)
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self._session.scalars(
            stmt.order_by(MoneyExpense.date.desc(), MoneyExpense.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(rows), int(total or 0)
