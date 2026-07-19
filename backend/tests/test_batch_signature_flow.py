"""Фича 13 «Пакетная подпись и учёт передачи» — статусная машина после выдачи.

Спека §2-§5: draft→to_issue→issued→signed→submitted. Печать/подпись собираются
ПАЧКОЙ после выдачи и статус выдачи не двигают. Проверяем:
  * batch-print создаёт пачку, ставит batch_id, статус остаётся issued;
  * mark-signed с исключением: часть → signed, исключённые остаются issued;
  * submit-to-accounting: signed → submitted с общим register_no;
  * счётчики четырёх фильтр-карточек;
  * реестр передачи по register_no.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.documents.schemas import (
    AcquisitionCreate,
    AcquisitionItemCreate,
    NotificationCreate,
    NotificationItemCreate,
)
from app.modules.documents.service import DocumentsService
from app.modules.issuance.schemas import RequestCreate, RequestItemCreate
from app.modules.issuance.service import IssuanceService
from app.shared.enums import RequestStatus
from app.shared.pagination import PageParams
from tests import constants as c

TODAY = dt.date.today()


async def _seed_stock(qty: str) -> None:
    async with SessionLocal() as s:
        notif = await DocumentsService(s).create_notification(
            author_id=c.ADMIN_ID,
            payload=NotificationCreate(
                date=TODAY,
                warehouse_id=c.WAREHOUSE_ISS,
                body_text="x",
                division_name="x",
                items=[NotificationItemCreate(product_id=c.PRODUCT_ID, qty_requested=Decimal(qty))],
            ),
        )
        nid = notif.id
    async with SessionLocal() as s:
        await DocumentsService(s).submit_notification(nid)
    async with SessionLocal() as s:
        await DocumentsService(s).create_acquisition(
            author_id=c.ADMIN_ID,
            payload=AcquisitionCreate(
                date=TODAY,
                notification_id=nid,
                warehouse_id=c.WAREHOUSE_ISS,
                items=[AcquisitionItemCreate(product_id=c.PRODUCT_ID, qty=Decimal(qty))],
            ),
        )


async def _make_issued_request(qty: str) -> int:
    """draft → confirm → issue, возвращает id заявки в статусе issued («К подписи»)."""
    async with SessionLocal() as s:
        req = await IssuanceService(s).create_request(
            employee_id=c.TEACHER_ID,
            payload=RequestCreate(
                warehouse_id=c.WAREHOUSE_ISS,
                reason="Материалы для занятий",
                items=[RequestItemCreate(product_id=c.PRODUCT_ID, qty=Decimal(qty))],
            ),
        )
        rid = req.id
    async with SessionLocal() as s:
        await IssuanceService(s).confirm_request(request_id=rid, employee_id=c.TEACHER_ID)
    async with SessionLocal() as s:
        await IssuanceService(s).issue_request(request_id=rid, author_id=c.ADMIN_ID)
    return rid


async def _status(session, rid: int) -> str:
    row = await session.execute(text("SELECT status FROM requests WHERE id=:i"), {"i": rid})
    return row.scalar_one()


async def _batch_id(session, rid: int) -> int | None:
    row = await session.execute(text("SELECT batch_id FROM requests WHERE id=:i"), {"i": rid})
    return row.scalar_one()


# ─────────────────────────────────────────────────────────────────────
# 1. batch-print: создаёт пачку, ставит batch_id, статус НЕ меняется.
# ─────────────────────────────────────────────────────────────────────


async def test_batch_print_groups_without_changing_status(session):
    await _seed_stock("100")
    r1 = await _make_issued_request("5")
    r2 = await _make_issued_request("7")

    async with SessionLocal() as s:
        batch, printed, skipped, _rendered = await IssuanceService(s).batch_print(
            ids=[r1, r2], created_by=c.ADMIN_ID
        )

    assert sorted(printed) == sorted([r1, r2])
    assert skipped == []
    assert batch.number.startswith("BATCH-")
    # Печать статус НЕ меняет (спека §3), но проставляет batch_id и printed_at.
    assert await _status(session, r1) == "issued"
    assert await _status(session, r2) == "issued"
    assert await _batch_id(session, r1) == batch.id
    assert await _batch_id(session, r2) == batch.id

    prow = await session.execute(
        text("SELECT printed_at FROM signature_batches WHERE id=:i"), {"i": batch.id}
    )
    assert prow.scalar_one() is not None


async def test_batch_print_skips_non_issued(session):
    """Заявка не в статусе issued не рушит пачку — уходит в skipped."""
    await _seed_stock("50")
    issued = await _make_issued_request("5")
    # to_issue (ещё не выдана) — не должна попасть в пачку.
    async with SessionLocal() as s:
        req = await IssuanceService(s).create_request(
            employee_id=c.TEACHER_ID,
            payload=RequestCreate(
                warehouse_id=c.WAREHOUSE_ISS,
                reason="ещё не выдана",
                items=[RequestItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("1"))],
            ),
        )
        not_issued = req.id
    async with SessionLocal() as s:
        await IssuanceService(s).confirm_request(
            request_id=not_issued, employee_id=c.TEACHER_ID
        )

    async with SessionLocal() as s:
        batch, printed, skipped, _ = await IssuanceService(s).batch_print(
            ids=[issued, not_issued], created_by=c.ADMIN_ID
        )
    assert printed == [issued]
    assert skipped == [not_issued]


# ─────────────────────────────────────────────────────────────────────
# 2. mark-signed с ИСКЛЮЧЕНИЕМ: 3 заявки, 1 исключить → 2 signed, 1 issued.
# ─────────────────────────────────────────────────────────────────────


async def test_mark_signed_with_exclusion(session):
    await _seed_stock("100")
    r1 = await _make_issued_request("3")
    r2 = await _make_issued_request("3")
    r3 = await _make_issued_request("3")

    async with SessionLocal() as s:
        batch, _printed, _skipped, _ = await IssuanceService(s).batch_print(
            ids=[r1, r2, r3], created_by=c.ADMIN_ID
        )

    # Подписаны только r1 и r3 — r2 исключён (не в списке), остаётся issued.
    async with SessionLocal() as s:
        signed, skipped = await IssuanceService(s).mark_signed(ids=[r1, r3])

    assert sorted(signed) == sorted([r1, r3])
    assert skipped == []
    assert await _status(session, r1) == "signed"
    assert await _status(session, r3) == "signed"
    assert await _status(session, r2) == "issued"  # исключённый остаётся issued

    # Пачке проставлен signed_at (есть подписанные заявки).
    srow = await session.execute(
        text("SELECT signed_at FROM signature_batches WHERE id=:i"), {"i": batch.id}
    )
    assert srow.scalar_one() is not None


# ─────────────────────────────────────────────────────────────────────
# 3. submit-to-accounting: signed → submitted, общий register_no.
# ─────────────────────────────────────────────────────────────────────


async def test_submit_to_accounting_assigns_common_register(session):
    await _seed_stock("100")
    r1 = await _make_issued_request("4")
    r2 = await _make_issued_request("4")

    async with SessionLocal() as s:
        await IssuanceService(s).batch_print(ids=[r1, r2], created_by=c.ADMIN_ID)
    async with SessionLocal() as s:
        await IssuanceService(s).mark_signed(ids=[r1, r2])

    async with SessionLocal() as s:
        register_no, submitted, skipped = await IssuanceService(
            s
        ).submit_to_accounting(ids=[r1, r2])

    assert sorted(submitted) == sorted([r1, r2])
    assert skipped == []
    assert register_no and register_no.startswith("REG-")
    assert await _status(session, r1) == "submitted"
    assert await _status(session, r2) == "submitted"

    rows = await session.execute(
        text(
            "SELECT submitted_at, submitted_register_no FROM requests "
            "WHERE id IN (:a,:b)"
        ),
        {"a": r1, "b": r2},
    )
    for submitted_at, reg in rows.all():
        assert submitted_at == TODAY
        assert reg == register_no  # ОДИН номер реестра на весь вызов

    # Реестр передачи по register_no содержит обе заявки.
    async with SessionLocal() as s:
        reg_rows, total = await IssuanceService(s).registry(
            PageParams(page=1, size=50), register_no=register_no
        )
    assert total == 2


async def test_submit_only_accepts_signed(session):
    """submit-to-accounting игнорирует не-signed заявки (issued остаётся issued)."""
    await _seed_stock("50")
    issued = await _make_issued_request("5")  # только issued, не signed

    async with SessionLocal() as s:
        register_no, submitted, skipped = await IssuanceService(
            s
        ).submit_to_accounting(ids=[issued])

    assert submitted == []
    assert skipped == [issued]
    assert register_no is None
    assert await _status(session, issued) == "issued"


# ─────────────────────────────────────────────────────────────────────
# 4. Счётчики четырёх фильтр-карточек (спека §5).
# ─────────────────────────────────────────────────────────────────────


async def test_status_counters_across_lifecycle(session):
    await _seed_stock("100")
    # to_issue: одна подтверждённая, не выданная.
    async with SessionLocal() as s:
        req = await IssuanceService(s).create_request(
            employee_id=c.TEACHER_ID,
            payload=RequestCreate(
                warehouse_id=c.WAREHOUSE_ISS,
                reason="к выдаче",
                items=[RequestItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("2"))],
            ),
        )
        to_issue_id = req.id
    async with SessionLocal() as s:
        await IssuanceService(s).confirm_request(
            request_id=to_issue_id, employee_id=c.TEACHER_ID
        )

    issued_id = await _make_issued_request("3")  # issued
    signed_id = await _make_issued_request("3")
    submitted_id = await _make_issued_request("3")

    async with SessionLocal() as s:
        await IssuanceService(s).mark_signed(ids=[signed_id])
    async with SessionLocal() as s:
        await IssuanceService(s).mark_signed(ids=[submitted_id])
    async with SessionLocal() as s:
        await IssuanceService(s).submit_to_accounting(ids=[submitted_id])

    async with SessionLocal() as s:
        svc = IssuanceService(s)
        counts = {
            "to_issue": await svc.count_by_status(status=RequestStatus.to_issue),
            "issued": await svc.count_by_status(status=RequestStatus.issued),
            "signed": await svc.count_by_status(status=RequestStatus.signed),
            "submitted": await svc.count_by_status(status=RequestStatus.submitted),
        }

    assert counts == {"to_issue": 1, "issued": 1, "signed": 1, "submitted": 1}
