"""М6 «Отчётность» — остатки, недокуп, история движений (keyset), ДДС.

Formalises verify_reports.py scenarios 1-4 (этап 6). Экспорт xlsx/pdf не
входит в приоритетный список инвариантов из задания (архитектура §9 требует
конкретно перезакупку/двойной issue()/минус кассы/списание сверх остатка —
все они уже покрыты test_documents_*/test_issuance_flow/test_cash), поэтому
здесь — только табличные данные отчётов, без сериализации в файл.
"""

import datetime as dt
from decimal import Decimal

from app.core.database import SessionLocal
from app.modules.cash.schemas import MoneyIncomeCreate
from app.modules.cash.service import CashService
from app.modules.documents.schemas import (
    AcquisitionCreate,
    AcquisitionItemCreate,
    NotificationCreate,
    NotificationItemCreate,
    TransferCreate,
    TransferItemCreate,
)
from app.modules.documents.service import DocumentsService
from app.modules.issuance.schemas import RequestCreate, RequestItemCreate
from app.modules.issuance.service import IssuanceService
from app.modules.reports.service import ReportsService
from app.shared.enums import UserCategory
from app.shared.pagination import PageParams
from tests import constants as c
from tests.conftest import TEST_CATALOG_PREFIX

# `expense_category` / `worker_user` fixtures come from conftest.py (used
# below via pytest's normal fixture injection — no explicit import needed).

TODAY = dt.date.today()


async def _notification(qty: str) -> int:
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
    # ОВ-11: отправляем в работу сразу — приобретать можно только против
    # «в работе»; submit один раз (в _acquire нельзя: закупок может быть несколько).
    async with SessionLocal() as s:
        await DocumentsService(s).submit_notification(nid)
    return nid


async def _acquire(nid: int, qty: str) -> None:
    async with SessionLocal() as s:
        await DocumentsService(s).create_acquisition(
            author_id=c.ADMIN_ID,
            payload=AcquisitionCreate(
                date=TODAY,
                notification_id=nid,
                warehouse_id=c.WAREHOUSE_ISS,
                supplier=f"{TEST_CATALOG_PREFIX}Поставщик",
                items=[AcquisitionItemCreate(product_id=c.PRODUCT_ID, qty=Decimal(qty), price=Decimal("1000"))],
            ),
        )


async def test_balances_report_reflects_purchases_and_transfers(session):
    nid = await _notification("10")
    await _acquire(nid, "10")
    async with SessionLocal() as s:
        await DocumentsService(s).create_transfer(
            author_id=c.ADMIN_ID,
            payload=TransferCreate(
                date=TODAY,
                from_warehouse_id=c.WAREHOUSE_ISS,
                to_warehouse_id=c.WAREHOUSE_NO,
                items=[TransferItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("3"))],
            ),
        )

    async with SessionLocal() as s:
        rows, _ = await ReportsService(s).list_balances(
            PageParams(page=1, size=50), product_id=c.PRODUCT_ID
        )
    by_wh = {r.warehouse_code: r.qty for r in rows}

    assert by_wh.get("W-ISS") == Decimal("7.000")
    assert by_wh.get("W-NO") == Decimal("3.000")


async def test_unpurchased_report_shows_remaining_and_excludes_closed(session):
    nid_closed = await _notification("10")
    await _acquire(nid_closed, "10")  # закроется полностью (SV-7)

    nid_open = await _notification("10")
    await _acquire(nid_open, "4")  # остаток к приобретению 6

    async with SessionLocal() as s:
        rows, _ = await ReportsService(s).list_unpurchased(
            PageParams(page=1, size=50), notification_id=nid_open
        )
        assert len(rows) == 1
        assert rows[0].qty_remaining == Decimal("6.000")

        rows_all, _ = await ReportsService(s).list_unpurchased(PageParams(page=1, size=50))
        ids = {r.notification_id for r in rows_all}
    assert nid_closed not in ids  # закрытое (10/10) не входит в недокуп


async def test_movements_report_signs_and_keyset_pagination(session):
    nid = await _notification("10")
    await _acquire(nid, "10")
    async with SessionLocal() as s:
        await DocumentsService(s).create_transfer(
            author_id=c.ADMIN_ID,
            payload=TransferCreate(
                date=TODAY,
                from_warehouse_id=c.WAREHOUSE_ISS,
                to_warehouse_id=c.WAREHOUSE_NO,
                items=[TransferItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("3"))],
            ),
        )
    # Расход через заявку: 4 движения всего (acquisition +10, transfer -3/+3,
    # writeoff -2).
    async with SessionLocal() as s:
        req = await IssuanceService(s).create_request(
            employee_id=c.TEACHER_ID,
            payload=RequestCreate(
                warehouse_id=c.WAREHOUSE_ISS,
                reason="нужно для работы",
                items=[RequestItemCreate(product_id=c.PRODUCT_ID, qty=Decimal("2"))],
            ),
        )
        rid = req.id
    async with SessionLocal() as s:
        await IssuanceService(s).confirm_request(request_id=rid, employee_id=c.TEACHER_ID)
    # Фича 13: выдача (списание) идёт прямо из to_issue, печать больше не шлюз.
    async with SessionLocal() as s:
        await IssuanceService(s).issue_request(request_id=rid, author_id=c.ADMIN_ID)

    async with SessionLocal() as s:
        svc = ReportsService(s)
        page1, cursor = await svc.list_movements(limit=2, product_id=c.PRODUCT_ID)
        assert len(page1) == 2
        assert cursor is not None

        all_rows, _ = await svc.list_movements(limit=50, product_id=c.PRODUCT_ID)
        signs = [(r.doc_type_label, r.qty) for r in all_rows]
        assert any(l == "Приобретение" and q > 0 for l, q in signs)
        assert any(l == "Перемещение" and q < 0 for l, q in signs)
        assert any(l == "Перемещение" and q > 0 for l, q in signs)
        assert any(l == "Расход" and q < 0 for l, q in signs)

        page2, _ = await svc.list_movements(limit=2, cursor=cursor, product_id=c.PRODUCT_ID)
        ids1 = {r.id for r in page1}
        ids2 = {r.id for r in page2}
        assert page2 and ids1.isdisjoint(ids2), "keyset: страницы не должны пересекаться"


async def test_cashflow_report_filters_by_category_with_correct_summary(
    session, expense_category, worker_user
):
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("500000"), date=TODAY
            ),
        )
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_WORKER, amount=Decimal("300000"), date=TODAY
            ),
        )

    from app.modules.auth.models import User
    from app.modules.cash.schemas import MoneyExpenseSubmission

    worker_id = worker_user

    async with SessionLocal() as s:
        teacher = await s.get(User, c.TEACHER_ID)
        await CashService(s).create_expense(
            user=teacher,
            payload=MoneyExpenseSubmission(
                expense_category_id=expense_category,
                amount=Decimal("150000"),
                description="бумага для учителя",
                date=TODAY,
            ),
            receipt_bytes=b"\x89PNG\r\n\x1a\n" + b"x" * 32,
        )
    async with SessionLocal() as s:
        worker = await s.get(User, worker_id)
        await CashService(s).create_expense(
            user=worker,
            payload=MoneyExpenseSubmission(
                expense_category_id=expense_category,
                amount=Decimal("90000"),
                description="хознужды работника",
                date=TODAY,
            ),
            receipt_bytes=b"\x89PNG\r\n\x1a\n" + b"x" * 32,
        )

    async with SessionLocal() as s:
        report = await ReportsService(s).cashflow(
            PageParams(page=1, size=50), category=UserCategory.teacher
        )
    assert len(report.items) == 1
    assert {r.employee_category for r in report.items} == {UserCategory.teacher}
    assert report.summary.total_income == Decimal("500000.00")
    assert report.summary.total_expense == Decimal("150000.00")
    bals = {b.cash_desk_type.value: b.balance for b in report.summary.desk_balances}
    assert bals["teacher"] == Decimal("350000.00")
    assert bals["worker"] == Decimal("210000.00")

    async with SessionLocal() as s:
        report_w = await ReportsService(s).cashflow(
            PageParams(page=1, size=50), category=UserCategory.worker
        )
    assert len(report_w.items) == 1
    assert report_w.summary.total_expense == Decimal("90000.00")
