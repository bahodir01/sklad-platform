"""Доступ к данным М6 «Отчётность» (архитектура §2 — без бизнес-правил).

Все запросы здесь — ЧТЕНИЕ. Отчёты ничего не пишут; единственный писатель
остатков — ledger (SV-2), денег — cash/service. Отчёты только собирают проекции
из уже готовых таблиц JOIN-ами.

Пагинация по access-паттернам ТЗ §4:
  * остатки (AP-10), недокуп (AP-6), ДДС (AP-8) — offset (наборы компактны,
    номера страниц заказчику удобнее курсора);
  * история движений (AP-5) — keyset, offset на длинной истории деградирует.
Для экспорта (xlsx/pdf) каждый отчёт умеет отдать ВЕСЬ набор (fetch_all) под
жёстким потолком строк EXPORT_ROW_CAP — тяжёлый экспорт задуман под Celery
(архитектура §8), где потолок снимается стримингом.
"""

import base64
import binascii
import datetime as dt
from decimal import Decimal
from typing import Any, NamedTuple

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.cash.models import CashDesk, MoneyExpense, MoneyIncome
from app.modules.catalog.models import ExpenseCategory, Product, Unit, Warehouse
from app.modules.documents.models import (
    Acquisition,
    AcquisitionItem,
    Notification,
    NotificationItem,
)
from app.modules.stock.models import StockBalance, StockMovement
from app.shared.enums import CashDeskType, MovementDocType
from app.shared.pagination import PageParams

# Потолок строк одного синхронного экспорта. Синхронная генерация (Celery/Redis
# в этой среде не подняты, §8 архитектуры) не должна тянуть в память миллионы
# строк истории. В фоновой задаче потолок заменяется server-side стримингом.
EXPORT_ROW_CAP = 100_000


# ── §8.1.3 keyset-курсор истории (тот же формат, что в stock/repository) ─


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


class CashflowTotals(NamedTuple):
    total_income: Decimal
    total_expense: Decimal


class ReportsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ══════════════════ §8.1.1 Остатки (AP-10) ══════════════════════

    def _balances_stmt(
        self,
        *,
        warehouse_id: int | None,
        product_id: int | None,
        unit_id: int | None,
    ) -> Select[Any]:
        stmt = (
            select(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.sku.label("sku"),
                Unit.id.label("unit_id"),
                Unit.code.label("unit_code"),
                Warehouse.id.label("warehouse_id"),
                Warehouse.code.label("warehouse_code"),
                Warehouse.name.label("warehouse_name"),
                StockBalance.qty.label("qty"),
            )
            .join(Product, StockBalance.product_id == Product.id)
            .join(Unit, Product.unit_id == Unit.id)
            .join(Warehouse, StockBalance.warehouse_id == Warehouse.id)
        )
        filters: list[Any] = []
        if warehouse_id is not None:
            filters.append(StockBalance.warehouse_id == warehouse_id)
        if product_id is not None:
            filters.append(StockBalance.product_id == product_id)
        if unit_id is not None:  # «единица» отчёта = products.unit_id (AP-10)
            filters.append(Product.unit_id == unit_id)
        if filters:
            stmt = stmt.where(*filters)
        return stmt.order_by(Warehouse.code, Product.name, Product.id)

    async def balances_page(
        self,
        params: PageParams,
        *,
        warehouse_id: int | None = None,
        product_id: int | None = None,
        unit_id: int | None = None,
    ) -> tuple[list[Any], int]:
        stmt = self._balances_stmt(
            warehouse_id=warehouse_id, product_id=product_id, unit_id=unit_id
        )
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        rows = (
            await self._session.execute(
                stmt.offset(params.offset).limit(params.limit)
            )
        ).all()
        return rows, int(total or 0)

    async def balances_all(
        self,
        *,
        warehouse_id: int | None = None,
        product_id: int | None = None,
        unit_id: int | None = None,
    ) -> list[Any]:
        stmt = self._balances_stmt(
            warehouse_id=warehouse_id, product_id=product_id, unit_id=unit_id
        )
        return (await self._session.execute(stmt.limit(EXPORT_ROW_CAP))).all()

    # ══════════════════ §8.1.2 Недокупленное (AP-6) ═════════════════

    def _unpurchased_stmt(
        self,
        *,
        notification_id: int | None,
        product_id: int | None,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> Select[Any]:
        # Уже приобретено по (уведомление, товар): SUM(acquisition_items.qty)
        # через acquisitions.notification_id. Расчётное, не хранится (ТЗ §3).
        purchased = (
            select(
                Acquisition.notification_id.label("notification_id"),
                AcquisitionItem.product_id.label("product_id"),
                func.coalesce(func.sum(AcquisitionItem.qty), 0).label("purchased"),
            )
            .join(AcquisitionItem, AcquisitionItem.acquisition_id == Acquisition.id)
            .group_by(Acquisition.notification_id, AcquisitionItem.product_id)
        ).subquery()

        purchased_qty = func.coalesce(purchased.c.purchased, 0)
        remaining = NotificationItem.qty_requested - purchased_qty

        stmt = (
            select(
                Notification.id.label("notification_id"),
                Notification.number.label("notification_number"),
                Notification.date.label("notification_date"),
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Unit.code.label("unit_code"),
                NotificationItem.qty_requested.label("qty_requested"),
                purchased_qty.label("qty_purchased"),
                remaining.label("qty_remaining"),
            )
            .join(Notification, NotificationItem.notification_id == Notification.id)
            .join(Product, NotificationItem.product_id == Product.id)
            .join(Unit, Product.unit_id == Unit.id)
            .outerjoin(
                purchased,
                and_(
                    purchased.c.notification_id == NotificationItem.notification_id,
                    purchased.c.product_id == NotificationItem.product_id,
                ),
            )
        )
        filters: list[Any] = [remaining > 0]  # только недокупленное (AP-6)
        if notification_id is not None:
            filters.append(NotificationItem.notification_id == notification_id)
        if product_id is not None:
            filters.append(NotificationItem.product_id == product_id)
        if date_from is not None:
            filters.append(Notification.date >= date_from)
        if date_to is not None:
            filters.append(Notification.date <= date_to)
        return (
            stmt.where(*filters)
            .order_by(Notification.date.desc(), Notification.id.desc(), Product.name)
        )

    async def unpurchased_page(
        self,
        params: PageParams,
        *,
        notification_id: int | None = None,
        product_id: int | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> tuple[list[Any], int]:
        stmt = self._unpurchased_stmt(
            notification_id=notification_id,
            product_id=product_id,
            date_from=date_from,
            date_to=date_to,
        )
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        rows = (
            await self._session.execute(
                stmt.offset(params.offset).limit(params.limit)
            )
        ).all()
        return rows, int(total or 0)

    async def unpurchased_all(
        self,
        *,
        notification_id: int | None = None,
        product_id: int | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> list[Any]:
        stmt = self._unpurchased_stmt(
            notification_id=notification_id,
            product_id=product_id,
            date_from=date_from,
            date_to=date_to,
        )
        return (await self._session.execute(stmt.limit(EXPORT_ROW_CAP))).all()

    # ══════════════════ §8.1.3 История движений (AP-5) ══════════════

    def _movements_stmt(
        self,
        *,
        product_id: int | None,
        warehouse_id: int | None,
        doc_type: MovementDocType | None,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> Select[Any]:
        stmt = (
            select(
                StockMovement.id.label("id"),
                StockMovement.created_at.label("created_at"),
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Unit.code.label("unit_code"),
                Warehouse.id.label("warehouse_id"),
                Warehouse.code.label("warehouse_code"),
                StockMovement.qty.label("qty"),
                StockMovement.doc_type.label("doc_type"),
                StockMovement.doc_id.label("doc_id"),
            )
            .join(Product, StockMovement.product_id == Product.id)
            .join(Unit, Product.unit_id == Unit.id)
            .join(Warehouse, StockMovement.warehouse_id == Warehouse.id)
        )
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
            # created_at это timestamptz, фильтр по дате → < следующего дня.
            filters.append(StockMovement.created_at < (date_to + dt.timedelta(days=1)))
        if filters:
            stmt = stmt.where(*filters)
        return stmt

    async def movements_keyset(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        product_id: int | None = None,
        warehouse_id: int | None = None,
        doc_type: MovementDocType | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> tuple[list[Any], str | None]:
        """AP-5: keyset по (created_at DESC, id DESC). Возвращает (страница,
        курсор_следующей). Ложится на композитный индекс stock_movements."""
        stmt = self._movements_stmt(
            product_id=product_id,
            warehouse_id=warehouse_id,
            doc_type=doc_type,
            date_from=date_from,
            date_to=date_to,
        )
        if cursor is not None:
            c_created, c_id = decode_cursor(cursor)
            stmt = stmt.where(
                (StockMovement.created_at, StockMovement.id) < (c_created, c_id)
            )
        stmt = stmt.order_by(
            StockMovement.created_at.desc(), StockMovement.id.desc()
        ).limit(limit + 1)  # +1: маркер наличия следующей страницы

        rows = (await self._session.execute(stmt)).all()
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return rows, next_cursor

    async def movements_all(
        self,
        *,
        product_id: int | None = None,
        warehouse_id: int | None = None,
        doc_type: MovementDocType | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> list[Any]:
        stmt = self._movements_stmt(
            product_id=product_id,
            warehouse_id=warehouse_id,
            doc_type=doc_type,
            date_from=date_from,
            date_to=date_to,
        ).order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        return (await self._session.execute(stmt.limit(EXPORT_ROW_CAP))).all()

    # ══════════════════ §8.2 ДДС (AP-8) ═════════════════════════════

    async def desk_by_type(self, desk_type: CashDeskType) -> CashDesk | None:
        return await self._session.scalar(
            select(CashDesk).where(CashDesk.type == desk_type)
        )

    async def desk_balances(self) -> list[CashDesk]:
        rows = await self._session.scalars(select(CashDesk).order_by(CashDesk.id))
        return list(rows)

    def _cashflow_stmt(
        self,
        *,
        cash_desk_id: int,
        expense_category_id: int | None,
        employee_id: int | None,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> Select[Any]:
        stmt = (
            select(
                MoneyExpense.id.label("id"),
                MoneyExpense.date.label("date"),
                User.id.label("employee_id"),
                User.full_name.label("employee_name"),
                User.category.label("employee_category"),
                CashDesk.id.label("cash_desk_id"),
                CashDesk.type.label("cash_desk_type"),
                ExpenseCategory.id.label("expense_category_id"),
                ExpenseCategory.name.label("expense_category_name"),
                MoneyExpense.amount.label("amount"),
                MoneyExpense.description.label("description"),
                MoneyExpense.receipt_url.label("receipt_object"),
            )
            .join(User, MoneyExpense.employee_id == User.id)
            .join(CashDesk, MoneyExpense.cash_desk_id == CashDesk.id)
            .join(
                ExpenseCategory,
                MoneyExpense.expense_category_id == ExpenseCategory.id,
            )
        )
        # §8.2/AP-8: фильтр по категории ОБЯЗАТЕЛЕН. Категория (teacher|worker)
        # разрешается в кассу этой категории — money_expense.cash_desk_id ложится
        # на индекс ix_money_expense_cash_desk_date (архитектура §4).
        filters: list[Any] = [MoneyExpense.cash_desk_id == cash_desk_id]
        if expense_category_id is not None:  # «вид расхода»
            filters.append(MoneyExpense.expense_category_id == expense_category_id)
        if employee_id is not None:  # «сотрудник»
            filters.append(MoneyExpense.employee_id == employee_id)
        if date_from is not None:
            filters.append(MoneyExpense.date >= date_from)
        if date_to is not None:
            filters.append(MoneyExpense.date <= date_to)
        return stmt.where(*filters).order_by(
            MoneyExpense.date.desc(), MoneyExpense.id.desc()
        )

    async def cashflow_page(
        self,
        params: PageParams,
        *,
        cash_desk_id: int,
        expense_category_id: int | None = None,
        employee_id: int | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> tuple[list[Any], int]:
        stmt = self._cashflow_stmt(
            cash_desk_id=cash_desk_id,
            expense_category_id=expense_category_id,
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        rows = (
            await self._session.execute(
                stmt.offset(params.offset).limit(params.limit)
            )
        ).all()
        return rows, int(total or 0)

    async def cashflow_all(
        self,
        *,
        cash_desk_id: int,
        expense_category_id: int | None = None,
        employee_id: int | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> list[Any]:
        stmt = self._cashflow_stmt(
            cash_desk_id=cash_desk_id,
            expense_category_id=expense_category_id,
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )
        return (await self._session.execute(stmt.limit(EXPORT_ROW_CAP))).all()

    async def cashflow_totals(
        self,
        *,
        cash_desk_id: int,
        expense_category_id: int | None = None,
        employee_id: int | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> CashflowTotals:
        """Итоги за период (ТЗ §8.2). Приход — по кассе категории за период
        (money_income не имеет сотрудника/вида расхода, поэтому эти фильтры к
        приходу не применяются). Расход — по всему отфильтрованному множеству."""
        exp_filters: list[Any] = [MoneyExpense.cash_desk_id == cash_desk_id]
        if expense_category_id is not None:
            exp_filters.append(MoneyExpense.expense_category_id == expense_category_id)
        if employee_id is not None:
            exp_filters.append(MoneyExpense.employee_id == employee_id)
        if date_from is not None:
            exp_filters.append(MoneyExpense.date >= date_from)
        if date_to is not None:
            exp_filters.append(MoneyExpense.date <= date_to)
        total_expense = await self._session.scalar(
            select(func.coalesce(func.sum(MoneyExpense.amount), 0)).where(*exp_filters)
        )

        inc_filters: list[Any] = [MoneyIncome.cash_desk_id == cash_desk_id]
        if date_from is not None:
            inc_filters.append(MoneyIncome.date >= date_from)
        if date_to is not None:
            inc_filters.append(MoneyIncome.date <= date_to)
        total_income = await self._session.scalar(
            select(func.coalesce(func.sum(MoneyIncome.amount), 0)).where(*inc_filters)
        )
        return CashflowTotals(
            total_income=Decimal(total_income or 0),
            total_expense=Decimal(total_expense or 0),
        )
