"""Pydantic v2-схемы М6 «Отчётность» (ТЗ §8).

ВАЖНО про контракт. reports — это ЧТЕНИЕ поверх готовых 22 таблиц; новых
таблиц/моделей модуль НЕ создаёт (задание этапа 6). Поэтому имена схем ниже
намеренно НЕ оканчиваются на Create/Update/Read/List и НЕ совпадают с именами
таблиц: валидатор контракта (contract_validator_sqlalchemy.py) привязывает к
таблице только схемы с этими суффиксами. Отчётные схемы — это транспортные
проекции JOIN-ов нескольких таблиц (money_expense+users, stock_balances+products
+warehouses+units и т.д.), у них нет своей таблицы, и это нормально.

Каждый отчёт отдаётся в трёх форматах (?format=json|xlsx|pdf, ТЗ §8.1.1/§8.2).
Эти схемы описывают ТОЛЬКО json-ветку; xlsx/pdf генерируются из тех же данных
в exporters.py (см. модульный docstring там).
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.shared.enums import CashDeskType, MovementDocType, UserCategory

# ── §8.1.1 Остатки в реальном времени (AP-10) ───────────────────────


class BalanceReportRow(BaseModel):
    """Строка отчёта остатков: проекция stock_balances + products + warehouses
    + units. Единица измерения приходит из products.unit_id (в остатках её нет)."""

    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    sku: str | None
    unit_id: int
    unit_code: str
    warehouse_id: int
    warehouse_code: str
    warehouse_name: str
    qty: Decimal  # проекция журнала, CHECK (qty >= 0)


# ── §8.1.2 Недокупленное по уведомлениям (AP-6) ─────────────────────


class UnpurchasedReportRow(BaseModel):
    """Остаток к приобретению = qty_requested − SUM(acquisition_items.qty).

    РАСЧЁТНОЕ значение, в БД не хранится (ТЗ §3, AP-6). В отчёт попадают только
    строки с остатком > 0.
    """

    model_config = ConfigDict(from_attributes=True)

    notification_id: int
    notification_number: str
    notification_date: dt.date
    product_id: int
    product_name: str
    unit_code: str
    qty_requested: Decimal
    qty_purchased: Decimal
    qty_remaining: Decimal


# ── §8.1.3 История движений (AP-5, keyset) ──────────────────────────


class MovementReportRow(BaseModel):
    """Строка хронологии движений: stock_movements + products + warehouses.

    qty знаковое (приход +, расход −). doc_type_label — русское название вида
    документа (Приобретение/Перемещение/Расход) для готового отчёта.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: dt.datetime
    product_id: int
    product_name: str
    unit_code: str
    warehouse_id: int
    warehouse_code: str
    qty: Decimal
    doc_type: MovementDocType
    doc_type_label: str
    doc_id: int


class MovementReportPage(BaseModel):
    """Keyset-страница истории (offset запрещён на длинной истории, AP-5)."""

    items: list[MovementReportRow]
    next_cursor: str | None = None
    limit: int


# ── §8.2 ДДС — движение денежных средств (AP-8) ─────────────────────


class CashflowReportRow(BaseModel):
    """Строка ДДС: money_expense JOIN users (ФИО, категория) + expense_categories
    (вид расхода). Сумма в UZS. receipt_url — presigned-ссылка на чек (TTL 5 мин,
    ТЗ §7); None в dev/локальном режиме без MinIO — тогда есть receipt_object."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    employee_id: int
    employee_name: str
    employee_category: UserCategory | None
    cash_desk_id: int
    cash_desk_type: CashDeskType
    expense_category_id: int
    expense_category_name: str
    amount: Decimal
    description: str
    receipt_object: str  # ключ bucket/key в хранилище
    receipt_url: str | None  # presigned URL (None, если MinIO не сконфигурирован)


class CashDeskBalance(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cash_desk_id: int
    cash_desk_type: CashDeskType
    balance: Decimal


class CashflowSummary(BaseModel):
    """Итоги ДДС за период по выбранной категории (кассе) + актуальные балансы
    обеих касс (ТЗ §8.2: «баланс каждой кассы, итоги прихода/расхода»)."""

    category: UserCategory
    date_from: dt.date | None
    date_to: dt.date | None
    total_income: Decimal  # приход по кассе категории за период
    total_expense: Decimal  # расход по отфильтрованному множеству
    net: Decimal  # приход − расход
    desk_balances: list[CashDeskBalance]  # актуальные балансы ОБЕИХ касс


class CashflowReport(BaseModel):
    """JSON-ответ ДДС: страница строк расхода + итоги/балансы."""

    items: list[CashflowReportRow]
    total: int
    page: int
    size: int
    pages: int
    summary: CashflowSummary
