"""М2 «Документооборот товаров» — приобретения (SV-1, SV-7).

Formalises stage2_scenarios.py scenarios 1, 2, 5, 6 (см. scratchpad
stage2_scenarios.py) into permanent regression tests.

Covers, per architecture §9's mandatory list and ТЗ §5:
  * SV-1 — контроль перезакупки (single request), text format per §4.2.
  * SV-1 — конкурентная перезакупка под FOR UPDATE (TOCTOU protection).
  * SV-7 — автозакрытие уведомления при полном приобретении.
  * Приход через ledger — баланс/движение согласуются с приобретённым qty.
"""

import asyncio
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.exceptions import DomainError
from app.modules.documents.schemas import (
    AcquisitionCreate,
    AcquisitionItemCreate,
    NotificationCreate,
    NotificationItemCreate,
)
from app.modules.documents.service import DocumentsService
from tests import constants as c

TODAY = dt.date.today()


async def _make_notification(
    qty_requested: str, *, warehouse_id: int = c.WAREHOUSE_ISS, submit: bool = True
) -> int:
    """Создать уведомление и (по умолчанию) отправить его в работу.

    Приобретения теперь возможны ТОЛЬКО против in_progress (ОВ-11): раньше
    первое приобретение само переводило draft→in_progress, теперь это делает
    отдельный submit. Тесты закупок хотят готовое к приобретению уведомление,
    поэтому по умолчанию сразу submit=True.
    """
    async with SessionLocal() as s:
        notif = await DocumentsService(s).create_notification(
            author_id=c.ADMIN_ID,
            payload=NotificationCreate(
                date=TODAY,
                warehouse_id=warehouse_id,
                body_text="Sizdan quyidagi tovarlarni ajratishingizni so'rayman:",
                division_name="Axborot texnologiyalari bo'limi",
                comment="Test",
                items=[
                    NotificationItemCreate(
                        product_id=c.PRODUCT_ID, qty_requested=Decimal(qty_requested)
                    )
                ],
            ),
        )
        nid = notif.id
    if submit:
        async with SessionLocal() as s:
            await DocumentsService(s).submit_notification(nid)
    return nid


async def _acquire(notification_id: int, qty: str, *, warehouse_id: int = c.WAREHOUSE_ISS):
    async with SessionLocal() as s:
        return await DocumentsService(s).create_acquisition(
            author_id=c.ADMIN_ID,
            payload=AcquisitionCreate(
                date=TODAY,
                notification_id=notification_id,
                warehouse_id=warehouse_id,
                supplier="ООО Канцтовары",
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


async def _notification_status(session, notification_id: int) -> str:
    row = await session.execute(
        text("SELECT status FROM notifications WHERE id=:i"), {"i": notification_id}
    )
    return row.scalar_one()


async def test_acquisition_posts_to_ledger_and_balance(session):
    """Приобретение 10 по уведомлению на 10 → приход +10, баланс 10 (§4.2)."""
    nid = await _make_notification("10")
    acq = await _acquire(nid, "10")

    bal = await _balance(session)
    mv = await session.execute(
        text(
            "SELECT qty, doc_type FROM stock_movements WHERE product_id=:p ORDER BY id"
        ),
        {"p": c.PRODUCT_ID},
    )
    rows = mv.all()

    assert bal == Decimal("10.000")
    assert len(rows) == 1
    assert Decimal(rows[0][0]) == Decimal("10")
    assert rows[0][1] == "acquisition"
    assert acq.number.startswith("ACQ-")


async def test_overbuy_rejected_with_sv1_error_format(session):
    """SV-1: остаток к приобретению 5, попытка купить 15 → отказ. Текст
    ошибки строго по §4.2: 'Товар "<name>": остаток к приобретению N <ед>,
    невозможно приобрести M <ед>'."""
    nid = await _make_notification("10")
    await _acquire(nid, "5")  # remaining = 5

    with pytest.raises(DomainError) as exc_info:
        await _acquire(nid, "15")

    message = exc_info.value.message
    assert exc_info.value.code == "overbuy"
    assert "остаток к приобретению 5" in message
    assert "невозможно приобрести 15" in message

    # Отказ не должен был ничего провести: остаток равен только первой закупке.
    assert await _balance(session) == Decimal("5.000")


async def test_overbuy_rejected_when_notification_fully_closed(session):
    """Остаток к приобретению 0 (уведомление закрыто) → любая докупка отказ."""
    nid = await _make_notification("10")
    await _acquire(nid, "10")
    assert await _notification_status(session, nid) == "closed"

    with pytest.raises(DomainError) as exc_info:
        await _acquire(nid, "1")
    # Закрытое уведомление отклоняется отдельной, более ранней проверкой.
    assert exc_info.value.code == "notification_closed"


async def test_autoclose_on_full_purchase_sv7(session):
    """SV-7: уведомление автоматически закрывается, когда остаток по всем
    строкам становится 0 за одно приобретение."""
    nid = await _make_notification("8")
    assert await _notification_status(session, nid) == "in_progress"

    await _acquire(nid, "8")

    assert await _notification_status(session, nid) == "closed"


async def test_submit_moves_draft_to_in_progress(session):
    """ОВ-11: submit — единственный переход draft→in_progress (не приобретение)."""
    nid = await _make_notification("10", submit=False)
    assert await _notification_status(session, nid) == "draft"

    async with SessionLocal() as s:
        await DocumentsService(s).submit_notification(nid)

    assert await _notification_status(session, nid) == "in_progress"


async def test_acquisition_against_draft_rejected(session):
    """ОВ-11: приобретать против черновика нельзя — сначала submit."""
    nid = await _make_notification("10", submit=False)
    assert await _notification_status(session, nid) == "draft"

    with pytest.raises(DomainError) as exc_info:
        await _acquire(nid, "1")
    assert exc_info.value.code == "notification_not_in_progress"
    # Отказ ничего не провёл.
    assert await _balance(session) == Decimal("0")


async def test_partial_purchase_keeps_in_progress(session):
    """Частичная закупка не закрывает и не меняет статус: остаётся in_progress."""
    nid = await _make_notification("10")
    await _acquire(nid, "4")
    assert await _notification_status(session, nid) == "in_progress"


async def test_concurrent_overbuy_protected_by_for_update(session):
    """ГЛАВНЫЙ ТЕСТ SV-1: два параллельных приобретения по 8 при потолке 10.

    Без FOR UPDATE на notification_items оба читают remaining=10 и оба
    проходят проверку (перезакупка до 16). С блокировкой — ровно одна
    проходит, вторая получает DomainError(code='overbuy'), суммарно
    приобретено не превышает 10 (AP-7, TOCTOU protection).
    """
    nid = await _make_notification("10")

    async def buy(qty: str) -> str:
        try:
            await _acquire(nid, qty)
            return "ok"
        except DomainError as exc:
            return f"rejected:{exc.code}"

    results = await asyncio.gather(buy("8"), buy("8"))

    oks = [r for r in results if r == "ok"]
    rejected = [r for r in results if r.startswith("rejected")]
    assert len(oks) == 1, f"ожидалась ровно одна успешная закупка, получили {results}"
    assert len(rejected) == 1
    assert rejected[0] == "rejected:overbuy"

    total = await session.execute(
        text(
            "SELECT COALESCE(SUM(ai.qty),0) FROM acquisition_items ai "
            "JOIN acquisitions a ON a.id = ai.acquisition_id "
            "WHERE a.notification_id = :n"
        ),
        {"n": nid},
    )
    purchased = Decimal(total.scalar_one())
    assert purchased <= Decimal("10")
    assert purchased == Decimal("8")  # ровно одна из двух закупок прошла

    # Остаток на складе должен отражать ровно то, что реально было куплено —
    # не 16 (обе закупки), не 0 (обе отклонены).
    assert await _balance(session) == Decimal("8.000")


async def test_duplicate_product_in_notification_items_rejected():
    """Товар не может повторяться дважды в строках одного уведомления."""
    with pytest.raises(DomainError) as exc_info:
        async with SessionLocal() as s:
            await DocumentsService(s).create_notification(
                author_id=c.ADMIN_ID,
                payload=NotificationCreate(
                    date=TODAY,
                    warehouse_id=c.WAREHOUSE_ISS,
                    body_text="x",
                    division_name="x",
                    items=[
                        NotificationItemCreate(product_id=c.PRODUCT_ID, qty_requested=Decimal("1")),
                        NotificationItemCreate(product_id=c.PRODUCT_ID, qty_requested=Decimal("2")),
                    ],
                ),
            )
    assert exc_info.value.code == "duplicate_product"
