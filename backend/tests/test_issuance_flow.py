"""М4 «Заявки и выдача» — статусная машина и issue() (ADR-2, спека13 §2).

Фича 13 расцепила выдачу и подпись: списание товара переехало на переход
to_issue → issued (было printed → issued). Печать/подпись собираются пачкой
позже и статус выдачи не двигают (см. test_batch_signature_flow.py).

Covers the two items architecture §9 calls mandatory: конкурентное списание
последнего товара при issue(), и защита от двойного issue().
"""

import asyncio
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.core.exceptions import ConflictError, InsufficientStock, ValidationError
from app.modules.documents.schemas import (
    AcquisitionCreate,
    AcquisitionItemCreate,
    NotificationCreate,
    NotificationItemCreate,
)
from app.modules.documents.service import DocumentsService
from app.modules.issuance.schemas import RequestCreate, RequestItemCreate
from app.modules.issuance.service import IssuanceService
from app.shared.pagination import PageParams
from tests import constants as c

TODAY = dt.date.today()


async def _seed_stock(qty: str, *, warehouse_id: int = c.WAREHOUSE_ISS) -> None:
    """Приход через полноценный документооборот (уведомление → приобретение)."""
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


async def _create_request(qty: str, *, warehouse_id: int = c.WAREHOUSE_ISS) -> int:
    async with SessionLocal() as s:
        req = await IssuanceService(s).create_request(
            employee_id=c.TEACHER_ID,
            payload=RequestCreate(
                warehouse_id=warehouse_id,
                reason="Материалы для занятий",
                items=[RequestItemCreate(product_id=c.PRODUCT_ID, qty=Decimal(qty))],
            ),
        )
        return req.id


async def _make_issuable_request(qty: str, *, warehouse_id: int = c.WAREHOUSE_ISS) -> int:
    """draft → confirm, возвращает id заявки в статусе to_issue («К выдаче»).

    Фича 13 (спека §2): выдача (issue) идёт прямо из to_issue — печать больше не
    шлюз, она собирается пачкой ПОСЛЕ выдачи."""
    rid = await _create_request(qty, warehouse_id=warehouse_id)
    async with SessionLocal() as s:
        await IssuanceService(s).confirm_request(request_id=rid, employee_id=c.TEACHER_ID)
    return rid


async def _balance(session, warehouse_id: int = c.WAREHOUSE_ISS) -> Decimal:
    row = await session.execute(
        text("SELECT qty FROM stock_balances WHERE product_id=:p AND warehouse_id=:w"),
        {"p": c.PRODUCT_ID, "w": warehouse_id},
    )
    r = row.first()
    return Decimal(r[0]) if r else Decimal("0")


async def _request_status(session, request_id: int) -> str:
    row = await session.execute(text("SELECT status FROM requests WHERE id=:i"), {"i": request_id})
    return row.scalar_one()


async def _inv2_holds(session) -> bool:
    """INV-2 (спека13 §2): (status IN issued/signed/submitted) ==
    (writeoff_id IS NOT NULL) для ВСЕХ заявок."""
    row = await session.execute(
        text(
            "SELECT count(*) FROM requests "
            "WHERE (status IN ('issued','signed','submitted')) "
            "!= (writeoff_id IS NOT NULL)"
        )
    )
    return row.scalar_one() == 0


# ─────────────────────────────────────────────────────────────────────
# 1. Остаток падает РОВНО на issue(), не на confirm (SV-4/спека13 §1).
# ─────────────────────────────────────────────────────────────────────


async def test_stock_untouched_until_issue_sv4(session):
    await _seed_stock("100")
    rid = await _create_request("10")
    b_draft = await _balance(session)

    async with SessionLocal() as s:
        await IssuanceService(s).confirm_request(request_id=rid, employee_id=c.TEACHER_ID)
    b_confirm = await _balance(session)

    # to_issue («К выдаче») — товар ещё НЕ списан (спека §1: списание в момент issue).
    assert b_draft == b_confirm == Decimal("100")
    assert await _request_status(session, rid) == "to_issue"


async def test_issue_posts_writeoff_and_drops_stock_exactly_once(session):
    await _seed_stock("100")
    rid = await _make_issuable_request("10")

    async with SessionLocal() as s:
        req_out, writeoff_out = await IssuanceService(s).issue_request(
            request_id=rid, author_id=c.ADMIN_ID
        )

    assert await _balance(session) == Decimal("90")  # 100 − 10 списано на issue()

    mv_count = await session.execute(
        text("SELECT count(*) FROM stock_movements WHERE doc_type='writeoff'")
    )
    assert mv_count.scalar_one() == 1

    assert writeoff_out.id is not None
    assert req_out.writeoff_id == writeoff_out.id
    assert req_out.status.value == "issued"
    assert await _inv2_holds(session)
    assert writeoff_out.number.startswith("WOFF-")


# ─────────────────────────────────────────────────────────────────────
# 2. ГЛАВНЫЙ ТЕСТ: двойной issue() (гонка) → ровно одна проводка.
# ─────────────────────────────────────────────────────────────────────


async def test_double_issue_race_yields_exactly_one_writeoff(session, new_session):
    """SV-5/INV-2: два ПАРАЛЛЕЛЬНЫХ issue() одной заявки.

    Остатка хватает на обе выдачи (50 ≥ 2×10) — это намеренно: второй issue()
    обязан упасть на условном UPDATE ... WHERE status='to_issue' (Conflict), а НЕ
    на нехватке товара (InsufficientStock). Так тест отделяет защиту от двойного
    списания (SV-5) от защиты остатка (SV-3).
    """
    await _seed_stock("50")
    rid = await _make_issuable_request("10")

    async def issue_once():
        async with new_session() as s:
            try:
                req_out, w_out = await IssuanceService(s).issue_request(
                    request_id=rid, author_id=c.ADMIN_ID
                )
                return ("ok", w_out.number)
            except ConflictError as exc:
                await s.rollback()
                return ("conflict", exc.code)
            except InsufficientStock as exc:
                await s.rollback()
                return ("insufficient", exc.message)

    results = await asyncio.gather(issue_once(), issue_once())
    outcomes = sorted(r[0] for r in results)

    assert outcomes == ["conflict", "ok"], f"ожидали 1 ok + 1 conflict, получили {results}"

    writeoff_count = await session.execute(text("SELECT count(*) FROM writeoffs"))
    assert writeoff_count.scalar_one() == 1, "должна быть создана РОВНО одна проводка"

    movement_count = await session.execute(
        text("SELECT count(*) FROM stock_movements WHERE doc_type='writeoff'")
    )
    assert movement_count.scalar_one() == 1, "товар должен быть списан ОДИН раз"

    assert await _balance(session) == Decimal("40")  # 50 − 10, списано ровно один раз
    assert await _inv2_holds(session)
    assert await _request_status(session, rid) == "issued"


async def test_double_issue_race_last_unit_of_stock(session, new_session):
    """Гонка за ПОСЛЕДНИЙ доступный товар (остаток == qty заявки). issue_request()
    берёт `FOR UPDATE` на stock_balances (ledger.post) РАНЬШЕ условного
    `UPDATE ... WHERE status='to_issue'` — проигравшая гонку транзакция видит
    остаток 0 и получает InsufficientStock. Ровно один успех, склад не в минус."""
    await _seed_stock("10")
    rid = await _make_issuable_request("10")  # ровно весь остаток

    async def issue_once():
        async with new_session() as s:
            try:
                await IssuanceService(s).issue_request(request_id=rid, author_id=c.ADMIN_ID)
                return "ok"
            except ConflictError:
                await s.rollback()
                return "conflict"
            except InsufficientStock:
                await s.rollback()
                return "insufficient"

    results = await asyncio.gather(issue_once(), issue_once())
    assert sorted(results) == ["insufficient", "ok"], f"получили {results}"
    assert results.count("ok") == 1, "ровно одна выдача должна пройти"

    bal = await _balance(session)
    assert bal == Decimal("0")  # ровно один раз списано 10 из 10 — не в минус (INV-1)
    assert bal >= Decimal("0")


async def test_inv2_check_is_immediate_not_deferrable(session):
    """Почему issue() обязан менять status и writeoff_id ОДНИМ UPDATE:
    попытка выставить status='issued', оставив writeoff_id=NULL, должна быть
    отвергнута БД НА ТОМ ЖЕ операторе — CHECK ck_requests_issued_iff_posted
    немедленный, не DEFERRABLE (спека13 §2 расширил его на signed/submitted)."""
    from sqlalchemy import update

    from app.modules.issuance.models import Request
    from app.shared.enums import RequestStatus

    await _seed_stock("50")
    rid = await _make_issuable_request("10")

    rejected = False
    async with SessionLocal() as s:
        try:
            await s.execute(
                update(Request)
                .where(Request.id == rid)
                .values(status=RequestStatus.issued)  # writeoff_id остаётся NULL
                .execution_options(synchronize_session=False)
            )
            await s.flush()
        except IntegrityError:
            rejected = True
        await s.rollback()

    assert rejected, "CHECK ck_requests_issued_iff_posted обязан сработать немедленно"
    # Заявка не должна была измениться отменённой попыткой.
    assert await _request_status(session, rid) == "to_issue"


# ─────────────────────────────────────────────────────────────────────
# 3. issue() при недостатке товара → InsufficientStock, статус остаётся
#    to_issue, проводки/движения нет (SV-3 применительно к issue()).
# ─────────────────────────────────────────────────────────────────────


async def test_issue_with_insufficient_stock_rolls_back_fully(session):
    await _seed_stock("5")
    rid = await _make_issuable_request("10")  # заявка на 10, на складе только 5

    with pytest.raises(InsufficientStock):
        async with SessionLocal() as s:
            await IssuanceService(s).issue_request(request_id=rid, author_id=c.ADMIN_ID)

    assert await _request_status(session, rid) == "to_issue"
    wc = await session.execute(text("SELECT count(*) FROM writeoffs"))
    assert wc.scalar_one() == 0
    mv = await session.execute(
        text("SELECT count(*) FROM stock_movements WHERE doc_type = 'writeoff'")
    )
    assert mv.scalar_one() == 0
    assert await _balance(session) == Decimal("5")


# ─────────────────────────────────────────────────────────────────────
# 4. SV-9: заявка возможна только со склада allows_issuance=true.
# ─────────────────────────────────────────────────────────────────────


async def test_request_from_non_issuance_warehouse_rejected_by_service():
    with pytest.raises(ValidationError) as exc_info:
        await _create_request("1", warehouse_id=c.WAREHOUSE_NO)
    assert exc_info.value.code == "warehouse_not_issuance"


async def test_request_from_non_issuance_warehouse_rejected_at_db_level(session):
    """Триггер requests_check_issuance_warehouse — последний рубеж SV-9,
    независимый от сервисного слоя."""
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO requests (number, employee_id, warehouse_id, reason) "
                    "VALUES ('REQ-TEST-DIRECT', :emp, :wh, 'обход сервиса')"
                ),
                {"emp": c.TEACHER_ID, "wh": c.WAREHOUSE_NO},
            )
            await s.commit()

    cnt = await session.execute(
        text("SELECT count(*) FROM requests WHERE number = 'REQ-TEST-DIRECT'")
    )
    assert cnt.scalar_one() == 0


# ─────────────────────────────────────────────────────────────────────
# 5. Row-level: «мои заявки» — только свои (§1.3).
# ─────────────────────────────────────────────────────────────────────


async def test_list_my_requests_is_row_level_scoped():
    await _create_request("2")

    async with SessionLocal() as s:
        mine, total_mine = await IssuanceService(s).list_my(
            PageParams(page=1, size=50), employee_id=c.TEACHER_ID
        )
        others, total_others = await IssuanceService(s).list_my(
            PageParams(page=1, size=50), employee_id=c.ADMIN_ID
        )

    assert total_mine == 1
    assert all(r.employee_id == c.TEACHER_ID for r in mine)
    assert total_others == 0
