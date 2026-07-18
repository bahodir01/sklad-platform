"""Роутер М3 (архитектура §6): GET /stock/balances, GET /stock/movements.

Доступ — ЛЮБАЯ роль (архитектура §6: «any (сотрудник — только чтение)»). На
этапе 2 было временно admin-only; этап 3 открывает чтение остатков сотрудникам:
форма заявки (AP-12/ОВ-5) подбирает товар и склад именно по /stock/balances.
Запись остатков по-прежнему невозможна снаружи — пишет только ledger (SV-2).
История движений — keyset-пагинация по AP-5, offset запрещён.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import ValidationError
from app.core.security import require_any_role
from app.modules.stock.schemas import MovementCursorPage, StockBalanceList, StockMovementList
from app.modules.stock.service import StockService
from app.shared.enums import MovementDocType
from app.shared.pagination import Page, PageParamsDep
from app.core.config import settings

router = APIRouter(tags=["stock"])

# Этап 3: чтение остатков/движений открыто любой роли (архитектура §6). Форма
# заявки сотрудника подбирает товар и склад по /stock/balances (AP-12/ОВ-5).
ReadAccess = Depends(require_any_role)


@router.get(
    "/stock/balances",
    response_model=Page[StockBalanceList],
    dependencies=[ReadAccess],
    summary="Остатки по складам (AP-10)",
)
async def list_balances(
    params: PageParamsDep,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    warehouse_id: Annotated[int | None, Query(ge=1)] = None,
    session: AsyncSession = Depends(get_session),
) -> Page[StockBalanceList]:
    items, total = await StockService(session).list_balances(
        params, product_id=product_id, warehouse_id=warehouse_id
    )
    return Page.build([StockBalanceList.model_validate(i) for i in items], total, params)


@router.get(
    "/stock/movements",
    response_model=MovementCursorPage,
    dependencies=[ReadAccess],
    summary="История движений, keyset-пагинация (AP-5)",
)
async def list_movements(
    cursor: Annotated[str | None, Query(description="Курсор следующей страницы")] = None,
    limit: Annotated[int, Query(ge=1, le=settings.page_size_max)] = settings.page_size_default,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    warehouse_id: Annotated[int | None, Query(ge=1)] = None,
    doc_type: Annotated[MovementDocType | None, Query()] = None,
    date_from: Annotated[dt.date | None, Query()] = None,
    date_to: Annotated[dt.date | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
) -> MovementCursorPage:
    try:
        rows, next_cursor = await StockService(session).list_movements(
            limit=limit,
            cursor=cursor,
            product_id=product_id,
            warehouse_id=warehouse_id,
            doc_type=doc_type,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError as exc:  # битый курсор
        raise ValidationError(str(exc), code="bad_cursor") from exc
    return MovementCursorPage(
        items=[StockMovementList.model_validate(r) for r in rows],
        next_cursor=next_cursor,
        limit=limit,
    )
