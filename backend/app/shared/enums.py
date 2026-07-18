"""Закрытые множества значений (ТЗ §5 «Enums»).

Имена PostgreSQL-типов берутся из 02-contract.json дословно:
user_role · user_category · catalog_status · notification_status ·
request_status · movement_doc_type · cash_desk_type.

Определены в одном месте, потому что catalog_status используется четырьмя
таблицами (products, warehouses, expense_types, expense_categories), а
дублирование определения enum-а — прямой путь к рассинхрону DDL и кода.
"""

from enum import Enum


class UserRole(str, Enum):
    """users.role — ТЗ §1: отдел закупки моделируется функцией admin."""

    admin = "admin"
    teacher = "teacher"
    worker = "worker"


class UserCategory(str, Enum):
    """users.category — определяет кассу сотрудника (SV-6). NULL ⟺ admin (INV-9)."""

    teacher = "teacher"
    worker = "worker"


class CatalogStatus(str, Enum):
    """SV-8: справочники не удаляются физически, только архивируются."""

    active = "active"
    archived = "archived"


class NotificationStatus(str, Enum):
    draft = "draft"
    in_progress = "in_progress"
    closed = "closed"


class RequestStatus(str, Enum):
    """Статусы принадлежат ЗАЯВКЕ, а не проводке (ADR-2)."""

    draft = "draft"
    to_print = "to_print"
    printed = "printed"
    issued = "issued"


class MovementDocType(str, Enum):
    acquisition = "acquisition"
    transfer = "transfer"
    writeoff = "writeoff"


class CashDeskType(str, Enum):
    teacher = "teacher"
    worker = "worker"
