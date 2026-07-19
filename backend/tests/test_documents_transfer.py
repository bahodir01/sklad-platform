"""М2 «Документооборот товаров» — перемещения (SV-3, INV-5, §4.3).

Formalises stage2_scenarios.py scenarios 3 and 4.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.exceptions import DomainError, InsufficientStock
from app.modules.documents.schemas import (
    AcquisitionCreate,
    AcquisitionItemCreate,
    NotificationCreate,
    NotificationItemCreate,
    TransferCreate,
    TransferItemCreate,
)
from app.modules.documents.service import DocumentsService
from tests import constants as c

TODAY = dt.date.today()


async def _seed_stock_via_acquisition(qty: str, *, warehouse_id: int = c.WAREHOUSE_ISS) -> None:
    """Приход товара через полноценный документооборот (уведомление →
    приобретение), а не напрямую через ledger — держит тест ближе к
    реальному сквозному пути."""
    async with SessionLocal() as s:
        notif = await DocumentsService(s).create_notification(
            author_id=c.ADMIN_ID,
            payload=NotificationCreate(
                date=TODAY,
                warehouse_id=warehouse_id,
                body_text="x",
                division_name="x",
                items=[NotificationItemCreate(product_id=c.PRODUCT_ID, qty_requested=Decimal(qty))],
            ),
        )
        nid = notif.id
    # ОВ-11: приобретать можно только против уведомления «в работе».
    async with SessionLocal() as s:
        await DocumentsService(s).submit_notification(nid)
    async with SessionLocal() as s:
        await DocumentsService(s).create_acquisition(
            author_id=c.ADMIN_ID,
            payload=AcquisitionCreate(
                date=TODAY,
                notification_id=nid,
                warehouse_id=warehouse_id,
                items=[AcquisitionItemCreate(product_id=c.PRODUCT_ID, qty=Decimal(qty))],
            ),
        )


async def _transfer(from_wh: int, to_wh: int, qty: str):
    async with SessionLocal() as s:
        return await DocumentsService(s).create_transfer(
            author_id=c.ADMIN_ID,
            payload=TransferCreate(
                date=TODAY,
                from_warehouse_id=from_wh,
                to_warehouse_id=to_wh,
                items=[TransferItemCreate(product_id=c.PRODUCT_ID, qty=Decimal(qty))],
            ),
        )


async def _balance(session, warehouse_id: int) -> Decimal:
    row = await session.execute(
        text("SELECT qty FROM stock_balances WHERE product_id=:p AND warehouse_id=:w"),
        {"p": c.PRODUCT_ID, "w": warehouse_id},
    )
    r = row.first()
    return Decimal(r[0]) if r else Decimal("0")


async def test_transfer_creates_two_movements_and_moves_balance(session):
    """§4.3: перемещение = ДВЕ записи ledger (−qty источник, +qty получатель)."""
    await _seed_stock_via_acquisition("15")

    tr = await _transfer(c.WAREHOUSE_ISS, c.WAREHOUSE_NO, "3")

    bal_iss = await _balance(session, c.WAREHOUSE_ISS)
    bal_no = await _balance(session, c.WAREHOUSE_NO)
    mv = await session.execute(
        text(
            "SELECT qty FROM stock_movements WHERE doc_type='transfer' AND product_id=:p ORDER BY id"
        ),
        {"p": c.PRODUCT_ID},
    )
    movements = [Decimal(r[0]) for r in mv.all()]

    assert bal_iss == Decimal("12.000")
    assert bal_no == Decimal("3.000")
    assert sorted(movements) == [Decimal("-3"), Decimal("3")]
    assert tr.number.startswith("TRF-")


async def test_transfer_over_stock_rejected_sv3(session):
    """SV-3: нельзя переместить больше, чем есть на складе-источнике. Отказ
    целиком откатывает транзакцию — баланс не должен измениться."""
    await _seed_stock_via_acquisition("3", warehouse_id=c.WAREHOUSE_NO)
    before = await _balance(session, c.WAREHOUSE_NO)

    with pytest.raises(InsufficientStock):
        await _transfer(c.WAREHOUSE_NO, c.WAREHOUSE_ISS, "999")

    after = await _balance(session, c.WAREHOUSE_NO)
    assert after == before == Decimal("3.000")
    # Получатель тоже не должен был получить приход — вся операция атомарна.
    assert await _balance(session, c.WAREHOUSE_ISS) == Decimal("0")


async def test_transfer_same_warehouse_rejected_inv5():
    """INV-5: склад-источник и склад-получатель должны различаться."""
    await _seed_stock_via_acquisition("5")

    with pytest.raises(DomainError) as exc_info:
        await _transfer(c.WAREHOUSE_ISS, c.WAREHOUSE_ISS, "1")
    assert exc_info.value.code == "same_warehouse"


async def test_transfer_allowed_to_and_from_non_issuance_warehouse(session):
    """Перемещение НЕ ограничено allows_issuance (только заявки — SV-9).
    W-NO не отмечен как склад списания, но перемещение с/на него работает."""
    await _seed_stock_via_acquisition("10", warehouse_id=c.WAREHOUSE_NO)

    await _transfer(c.WAREHOUSE_NO, c.WAREHOUSE_ISS, "4")

    assert await _balance(session, c.WAREHOUSE_NO) == Decimal("6.000")
    assert await _balance(session, c.WAREHOUSE_ISS) == Decimal("4.000")
