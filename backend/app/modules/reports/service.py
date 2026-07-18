"""Оркестрация М6 «Отчётность». Архитектура §2: read-only путь, транзакция не
открывается — отчёты ничего не пишут.

Сервис отдаёт данные в двух видах:
  * JSON — типизированные схемы/страницы (для ?format=json);
  * ReportTable — формат-независимая таблица для exporters.export_table()
    (для ?format=xlsx|pdf). Сбор данных отделён от генерации файла ровно ради
    тривиального выноса экспорта в Celery (см. docstring exporters.py).
"""

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.modules.reports.exporters import Column, ReportTable
from app.modules.reports.repository import ReportsRepository
from app.modules.reports.schemas import (
    CashDeskBalance,
    CashflowReport,
    CashflowReportRow,
    CashflowSummary,
    MovementReportRow,
)
from app.shared.enums import CashDeskType, MovementDocType, UserCategory
from app.shared.pagination import PageParams
from app.shared.storage import presigned_url

# Вид документа движения → русское название для готового отчёта (ТЗ §8.1.3).
_DOC_TYPE_LABEL: dict[MovementDocType, str] = {
    MovementDocType.acquisition: "Приобретение",
    MovementDocType.transfer: "Перемещение",
    MovementDocType.writeoff: "Расход",
}


def _fmt_qty(value: Decimal | None) -> str:
    """Количество без хвостовых нулей: 7.000 → «7», 3.500 → «3.5»."""
    if value is None:
        return ""
    return format(Decimal(value).normalize(), "f")


def _fmt_money(value: Decimal | None) -> str:
    """Сумма UZS с двумя знаками: 150000 → «150000.00»."""
    return f"{Decimal(value or 0):.2f}"


def _receipt_presigned(receipt_object: str) -> str | None:
    """receipt_url в БД хранится как «bucket/key». Presigned URL (TTL 5 мин,
    ТЗ §7) требует раздельные bucket и key. None в dev/локальном режиме (MinIO
    не сконфигурирован) — тогда у клиента остаётся receipt_object."""
    if not receipt_object or "/" not in receipt_object:
        return None
    bucket, key = receipt_object.split("/", 1)
    return presigned_url(bucket, key)


class ReportsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ReportsRepository(session)

    # ══════════════════ §8.1.1 Остатки (AP-10) ══════════════════════

    async def list_balances(
        self,
        params: PageParams,
        *,
        warehouse_id: int | None = None,
        product_id: int | None = None,
        unit_id: int | None = None,
    ) -> tuple[list[Any], int]:
        return await self._repo.balances_page(
            params, warehouse_id=warehouse_id, product_id=product_id, unit_id=unit_id
        )

    async def build_balances_table(
        self,
        *,
        warehouse_id: int | None = None,
        product_id: int | None = None,
        unit_id: int | None = None,
    ) -> ReportTable:
        rows = await self._repo.balances_all(
            warehouse_id=warehouse_id, product_id=product_id, unit_id=unit_id
        )
        return ReportTable(
            title="Остатки на складах",
            slug="balances",
            columns=[
                Column("warehouse_code", "Код склада"),
                Column("warehouse_name", "Склад"),
                Column("product_name", "Номенклатура"),
                Column("sku", "Артикул"),
                Column("unit_code", "Ед."),
                Column("qty", "Остаток", numeric=True),
            ],
            rows=[
                {
                    "warehouse_code": r.warehouse_code,
                    "warehouse_name": r.warehouse_name,
                    "product_name": r.product_name,
                    "sku": r.sku or "",
                    "unit_code": r.unit_code,
                    "qty": r.qty,
                }
                for r in rows
            ],
        )

    # ══════════════════ §8.1.2 Недокупленное (AP-6) ═════════════════

    async def list_unpurchased(
        self,
        params: PageParams,
        *,
        notification_id: int | None = None,
        product_id: int | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> tuple[list[Any], int]:
        return await self._repo.unpurchased_page(
            params,
            notification_id=notification_id,
            product_id=product_id,
            date_from=date_from,
            date_to=date_to,
        )

    async def build_unpurchased_table(
        self,
        *,
        notification_id: int | None = None,
        product_id: int | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> ReportTable:
        rows = await self._repo.unpurchased_all(
            notification_id=notification_id,
            product_id=product_id,
            date_from=date_from,
            date_to=date_to,
        )
        return ReportTable(
            title="Недокупленное по уведомлениям",
            slug="unpurchased",
            columns=[
                Column("notification_number", "Уведомление"),
                Column("notification_date", "Дата"),
                Column("product_name", "Номенклатура"),
                Column("unit_code", "Ед."),
                Column("qty_requested", "Запрошено", numeric=True),
                Column("qty_purchased", "Приобретено", numeric=True),
                Column("qty_remaining", "К приобретению", numeric=True),
            ],
            rows=[
                {
                    "notification_number": r.notification_number,
                    "notification_date": r.notification_date,
                    "product_name": r.product_name,
                    "unit_code": r.unit_code,
                    "qty_requested": r.qty_requested,
                    "qty_purchased": r.qty_purchased,
                    "qty_remaining": r.qty_remaining,
                }
                for r in rows
            ],
        )

    # ══════════════════ §8.1.3 История движений (AP-5) ══════════════

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
    ) -> tuple[list[MovementReportRow], str | None]:
        rows, next_cursor = await self._repo.movements_keyset(
            limit=limit,
            cursor=cursor,
            product_id=product_id,
            warehouse_id=warehouse_id,
            doc_type=doc_type,
            date_from=date_from,
            date_to=date_to,
        )
        return [self._movement_row(r) for r in rows], next_cursor

    @staticmethod
    def _movement_row(r: Any) -> MovementReportRow:
        return MovementReportRow(
            id=r.id,
            created_at=r.created_at,
            product_id=r.product_id,
            product_name=r.product_name,
            unit_code=r.unit_code,
            warehouse_id=r.warehouse_id,
            warehouse_code=r.warehouse_code,
            qty=r.qty,
            doc_type=r.doc_type,
            doc_type_label=_DOC_TYPE_LABEL.get(r.doc_type, r.doc_type.value),
            doc_id=r.doc_id,
        )

    async def build_movements_table(
        self,
        *,
        product_id: int | None = None,
        warehouse_id: int | None = None,
        doc_type: MovementDocType | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> ReportTable:
        rows = await self._repo.movements_all(
            product_id=product_id,
            warehouse_id=warehouse_id,
            doc_type=doc_type,
            date_from=date_from,
            date_to=date_to,
        )
        return ReportTable(
            title="История движений",
            slug="movements",
            columns=[
                Column("created_at", "Дата/время"),
                Column("doc_type_label", "Вид документа"),
                Column("doc_id", "№ документа"),
                Column("warehouse_code", "Склад"),
                Column("product_name", "Номенклатура"),
                Column("unit_code", "Ед."),
                Column("qty", "Кол-во (±)", numeric=True),
            ],
            rows=[
                {
                    "created_at": r.created_at,
                    "doc_type_label": _DOC_TYPE_LABEL.get(r.doc_type, r.doc_type.value),
                    "doc_id": r.doc_id,
                    "warehouse_code": r.warehouse_code,
                    "product_name": r.product_name,
                    "unit_code": r.unit_code,
                    "qty": r.qty,
                }
                for r in rows
            ],
        )

    # ══════════════════ §8.2 ДДС (AP-8) ═════════════════════════════

    async def _resolve_desk(self, category: UserCategory) -> Any:
        """§8.2/AP-8: обязательная категория (teacher|worker) → касса этой
        категории. Касса определяет множество расходов и приход для итогов."""
        desk = await self._repo.desk_by_type(CashDeskType(category.value))
        if desk is None:  # pragma: no cover — кассы засеяны начальной миграцией
            raise ValidationError(
                f"Касса категории «{category.value}» не найдена",
                code="cash_desk_missing",
            )
        return desk

    async def cashflow(
        self,
        params: PageParams,
        *,
        category: UserCategory,
        expense_category_id: int | None = None,
        employee_id: int | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> CashflowReport:
        desk = await self._resolve_desk(category)
        rows, total = await self._repo.cashflow_page(
            params,
            cash_desk_id=desk.id,
            expense_category_id=expense_category_id,
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )
        items = [
            CashflowReportRow(
                id=r.id,
                date=r.date,
                employee_id=r.employee_id,
                employee_name=r.employee_name,
                employee_category=r.employee_category,
                cash_desk_id=r.cash_desk_id,
                cash_desk_type=r.cash_desk_type,
                expense_category_id=r.expense_category_id,
                expense_category_name=r.expense_category_name,
                amount=r.amount,
                description=r.description,
                receipt_object=r.receipt_object,
                receipt_url=_receipt_presigned(r.receipt_object),
            )
            for r in rows
        ]
        summary = await self._cashflow_summary(
            desk_id=desk.id,
            category=category,
            expense_category_id=expense_category_id,
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )
        pages = (total + params.size - 1) // params.size if params.size else 0
        return CashflowReport(
            items=items,
            total=total,
            page=params.page,
            size=params.size,
            pages=pages,
            summary=summary,
        )

    async def _cashflow_summary(
        self,
        *,
        desk_id: int,
        category: UserCategory,
        expense_category_id: int | None,
        employee_id: int | None,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> CashflowSummary:
        totals = await self._repo.cashflow_totals(
            cash_desk_id=desk_id,
            expense_category_id=expense_category_id,
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )
        desks = await self._repo.desk_balances()
        return CashflowSummary(
            category=category,
            date_from=date_from,
            date_to=date_to,
            total_income=totals.total_income,
            total_expense=totals.total_expense,
            net=totals.total_income - totals.total_expense,
            desk_balances=[
                CashDeskBalance(
                    cash_desk_id=d.id, cash_desk_type=d.type, balance=d.balance
                )
                for d in desks
            ],
        )

    async def build_cashflow_table(
        self,
        *,
        category: UserCategory,
        expense_category_id: int | None = None,
        employee_id: int | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> ReportTable:
        desk = await self._resolve_desk(category)
        rows = await self._repo.cashflow_all(
            cash_desk_id=desk.id,
            expense_category_id=expense_category_id,
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )
        summary = await self._cashflow_summary(
            desk_id=desk.id,
            category=category,
            expense_category_id=expense_category_id,
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )
        summary_lines: list[tuple[str, str]] = [
            (f"Итого приход (касса «{category.value}»)", _fmt_money(summary.total_income)),
            ("Итого расход (по фильтру)", _fmt_money(summary.total_expense)),
            ("Сальдо (приход − расход)", _fmt_money(summary.net)),
        ]
        for d in summary.desk_balances:
            summary_lines.append(
                (f"Баланс кассы «{d.cash_desk_type.value}»", _fmt_money(d.balance))
            )
        return ReportTable(
            title=f"ДДС — касса «{category.value}»",
            slug="cashflow",
            columns=[
                Column("date", "Дата"),
                Column("employee_name", "ФИО"),
                Column("employee_category", "Категория"),
                Column("expense_category_name", "Вид расхода"),
                Column("amount", "Сумма, UZS", numeric=True),
                Column("description", "Назначение"),
            ],
            rows=[
                {
                    "date": r.date,
                    "employee_name": r.employee_name,
                    "employee_category": (
                        r.employee_category.value if r.employee_category else ""
                    ),
                    "expense_category_name": r.expense_category_name,
                    "amount": r.amount,
                    "description": r.description,
                }
                for r in rows
            ],
            summary=summary_lines,
        )
