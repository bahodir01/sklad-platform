"""Доступ к данным М3 (чтение). Бизнес-правил здесь нет (архитектура §2).

Запись в stock_movements/stock_balances идёт ТОЛЬКО через ledger.post (SV-2) —
методов вставки/обновления в этом репозитории намеренно нет.
"""

import base64
import binascii
import datetime as dt
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stock.models import StockBalance, StockMovement
from app.shared.enums import MovementDocType
from app.shared.pagination import PageParams


class StockBalanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        params: PageParams,
        *,
        product_id: int | None = None,
        warehouse_id: int | None = None,
    ) -> tuple[list[StockBalance], int]:
        """AP-10: остатки по складам, offset-пагинация (справочник остатков
        компактен, номера страниц удобнее курсора). Историю (AP-5) — keyset."""
        stmt: Select[tuple[StockBalance]] = select(StockBalance)
        if product_id is not None:
            stmt = stmt.where(StockBalance.product_id == product_id)
        if warehouse_id is not None:
            stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)

        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self._session.scalars(
            stmt.order_by(StockBalance.warehouse_id, StockBalance.product_id)
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(rows), int(total or 0)


# ── Keyset-курсор истории движений (AP-5) ───────────────────────────
# Курсор — непрозрачная строка base64("<created_at_iso>|<id>"). Сортировка
# (created_at DESC, id DESC) — ровно под композитный индекс из models.py.
# offset здесь запрещён (AP-5): на длинной истории он деградирует, keyset —
# нет, потому что идёт по индексу от границы курсора.


def encode_cursor(created_at: dt.datetime, movement_id: int) -> str:
    raw = f"{created_at.isoformat()}|{movement_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[dt.datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_str, id_str = raw.rsplit("|", 1)
        return dt.datetime.fromisoformat(created_str), int(id_str)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Некорректный курсор пагинации") from exc


class StockMovementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_keyset(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        product_id: int | None = None,
        warehouse_id: int | None = None,
        doc_type: MovementDocType | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> tuple[list[StockMovement], str | None]:
        """AP-5: keyset-пагинация. Возвращает (страница, курсор_следующей)."""
        stmt: Select[tuple[StockMovement]] = select(StockMovement)

        filters: list[Any] = []
        if product_id is not None:
            filters.append(StockMovement.product_id == product_id)
        if warehouse_id is not None:
            filters.append(StockMovement.warehouse_id == warehouse_id)
        if doc_type is not None:
            filters.append(StockMovement.doc_type == doc_type)
        if date_from is not None:
            filters.append(StockMovement.created_at >= date_from)
        if date_to is not None:
            # < следующего дня: created_at это timestamptz, а фильтр по дате.
            filters.append(
                StockMovement.created_at < (date_to + dt.timedelta(days=1))
            )
        if filters:
            stmt = stmt.where(*filters)

        if cursor is not None:
            c_created, c_id = decode_cursor(cursor)
            # Строгое «(created_at, id) < (курсор)» — идём по индексу дальше
            # последней отданной строки, без пропусков и дублей на равных ts.
            stmt = stmt.where(
                (StockMovement.created_at, StockMovement.id) < (c_created, c_id)
            )

        # limit + 1: лишняя строка сообщает, есть ли следующая страница.
        stmt = stmt.order_by(
            StockMovement.created_at.desc(), StockMovement.id.desc()
        ).limit(limit + 1)

        rows = list(await self._session.scalars(stmt))
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return rows, next_cursor
