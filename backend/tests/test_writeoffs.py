"""§4.4 Порча / брак — прямое списание без заявки (INV-4, SV-9 неприменим).

Formalises verify_stage45.py scenarios t1-t3 (этап 4).
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.exceptions import ValidationError
from app.modules.documents.schemas import (
    AcquisitionCreate,
    AcquisitionItemCreate,
    NotificationCreate,
    NotificationItemCreate,
)
from app.modules.documents.service import DocumentsService
from app.modules.issuance.schemas import WriteoffCreate, WriteoffItemCreate
from app.modules.issuance.service import IssuanceService
from tests import constants as c

TODAY = dt.date.today()


async def _seed_stock(qty: str, *, warehouse_id: int = c.WAREHOUSE_ISS) -> None:
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


async def _balance(session, warehouse_id: int = c.WAREHOUSE_ISS) -> Decimal:
    row = await session.execute(
        text("SELECT qty FROM stock_balances WHERE product_id=:p AND warehouse_id=:w"),
        {"p": c.PRODUCT_ID, "w": warehouse_id},
    )
    r = row.first()
    return Decimal(r[0]) if r else Decimal("0")


async def test_spoilage_writeoff_ok_no_employee(session):
    """Порча 5 шт: движение −5, employee_id=NULL, requires_employee=False."""
    await _seed_stock("100")
    bal_before = await _balance(session)

    async with SessionLocal() as s:
        wo = await IssuanceService(s).create_writeoff(
            author_id=c.ADMIN_ID,
            payload=WriteoffCreate(
                date=TODAY,
                warehouse_id=c.WAREHOUSE_ISS,
                expense_type_id=c.EXPENSE_TYPE_SPOILAGE,
                employee_id=None,
                items=[WriteoffItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("5"), reason="намокла")],
            ),
        )

    assert wo.employee_id is None
    assert wo.requires_employee is False
    assert wo.number.startswith("WOFF-")

    mv = await session.execute(
        text("SELECT qty FROM stock_movements WHERE doc_type='writeoff' AND doc_id=:i"),
        {"i": wo.id},
    )
    row = mv.first()
    assert row is not None and Decimal(row[0]) == Decimal("-5.000")
    assert await _balance(session) == bal_before - Decimal("5")


async def test_spoilage_with_employee_rejected_inv4():
    """INV-4: при типе «Порча» (requires_employee=false) сотрудник запрещён."""
    await _seed_stock("10")
    with pytest.raises(ValidationError) as exc_info:
        async with SessionLocal() as s:
            await IssuanceService(s).create_writeoff(
                author_id=c.ADMIN_ID,
                payload=WriteoffCreate(
                    date=TODAY,
                    warehouse_id=c.WAREHOUSE_ISS,
                    expense_type_id=c.EXPENSE_TYPE_SPOILAGE,
                    employee_id=c.TEACHER_ID,  # запрещено
                    items=[WriteoffItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("1"))],
                ),
            )
    assert exc_info.value.code == "employee_forbidden"


async def test_issuance_type_rejected_on_direct_writeoff_endpoint():
    """Тип «Выдача» (requires_employee=true) не может проводиться через
    POST /writeoffs — только через заявку/issue() (ADR-2, этап 3)."""
    await _seed_stock("10")
    with pytest.raises(ValidationError) as exc_info:
        async with SessionLocal() as s:
            await IssuanceService(s).create_writeoff(
                author_id=c.ADMIN_ID,
                payload=WriteoffCreate(
                    date=TODAY,
                    warehouse_id=c.WAREHOUSE_ISS,
                    expense_type_id=c.EXPENSE_TYPE_ISSUANCE,
                    employee_id=None,
                    items=[WriteoffItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("1"))],
                ),
            )
    assert exc_info.value.code == "issuance_via_request"


async def test_spoilage_allowed_on_non_issuance_warehouse(session):
    """Порча/брак НЕ ограничены allows_issuance (SV-9 распространяется
    только на requests) — товар может испортиться на любом складе."""
    await _seed_stock("10", warehouse_id=c.WAREHOUSE_NO)

    async with SessionLocal() as s:
        wo = await IssuanceService(s).create_writeoff(
            author_id=c.ADMIN_ID,
            payload=WriteoffCreate(
                date=TODAY,
                warehouse_id=c.WAREHOUSE_NO,  # allows_issuance=false — разрешено
                expense_type_id=c.EXPENSE_TYPE_SPOILAGE,
                employee_id=None,
                items=[WriteoffItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("2"))],
            ),
        )
    assert wo.id is not None
    assert await _balance(session, c.WAREHOUSE_NO) == Decimal("8")


async def test_spoilage_over_stock_rejected():
    """SV-3 применительно к прямому списанию: нельзя списать больше остатка."""
    from app.core.exceptions import InsufficientStock

    await _seed_stock("3")
    with pytest.raises(InsufficientStock):
        async with SessionLocal() as s:
            await IssuanceService(s).create_writeoff(
                author_id=c.ADMIN_ID,
                payload=WriteoffCreate(
                    date=TODAY,
                    warehouse_id=c.WAREHOUSE_ISS,
                    expense_type_id=c.EXPENSE_TYPE_SPOILAGE,
                    employee_id=None,
                    items=[WriteoffItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("999"))],
                ),
            )
