"""Pydantic v2-схемы М3. Состав задают API-флаги 02-contract.json.

stock_movements и stock_balances — read-only снаружи (SV-2: писать может только
ledger.post). Поэтому у обеих таблиц create=false / update=false во всех полях —
схем Create/Update здесь нет и быть не должно, только List/Read.

Карта флагов (все поля обеих таблиц: get_index=✓ get_single=✓ create=✗ update=✗):

  stock_movements: id, product_id, warehouse_id, qty, doc_type, doc_id, created_at
  stock_balances:  id, product_id, warehouse_id, qty
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.shared.enums import MovementDocType

# ── stock_movements ─────────────────────────────────────────────────


class StockMovementList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    warehouse_id: int
    qty: Decimal  # знаковое: приход +, расход −
    doc_type: MovementDocType
    doc_id: int
    created_at: dt.datetime


class StockMovementRead(StockMovementList):
    """get_single-состав совпадает с get_index — наследуем, а не копируем."""


# ── stock_balances ──────────────────────────────────────────────────


class StockBalanceList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    warehouse_id: int
    qty: Decimal  # проекция журнала, CHECK (qty >= 0)


class StockBalanceRead(StockBalanceList):
    pass


# ── Ответ keyset-пагинации истории движений (AP-5) ──────────────────
# Имя НЕ оканчивается на Create/Update/Read/List → валидатор контракта его
# не привязывает к таблице и не проверяет: это транспортный конверт, а не
# проекция сущности.


class MovementCursorPage(BaseModel):
    """Страница истории движений с курсором на следующую (offset запрещён AP-5)."""

    items: list[StockMovementList]
    next_cursor: str | None = None
    limit: int
