"""Чтение остатков и истории движений (М3). Архитектура §6: M3 — только чтение
снаружи, запись остатков идёт исключительно через ledger.post (SV-2).

Транзакция не открывается: это read-only путь. Запись (ledger) живёт в
транзакциях документов (documents/service.py).
"""

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stock.repository import (
    StockBalanceRepository,
    StockMovementRepository,
)
from app.shared.enums import MovementDocType
from app.shared.pagination import PageParams


class StockService:
    def __init__(self, session: AsyncSession) -> None:
        self._balances = StockBalanceRepository(session)
        self._movements = StockMovementRepository(session)

    async def list_balances(
        self,
        params: PageParams,
        *,
        product_id: int | None = None,
        warehouse_id: int | None = None,
    ):
        return await self._balances.list(
            params, product_id=product_id, warehouse_id=warehouse_id
        )

    async def list_movements(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        product_id: int | None = None,
        warehouse_id: int | None = None,
        doc_type: MovementDocType | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ):
        return await self._movements.list_keyset(
            limit=limit,
            cursor=cursor,
            product_id=product_id,
            warehouse_id=warehouse_id,
            doc_type=doc_type,
            date_from=date_from,
            date_to=date_to,
        )
