"""Реестр всех 22 моделей схемы.

Модели живут в modules/*/models.py (архитектура §3: модуль — единица владения).
Этот файл их только собирает, и нужен он двум потребителям:

  * alembic/env.py — target_metadata должен видеть ВСЕ таблицы, иначе
    autogenerate предложит удалить те, чей модуль не импортирован;
  * валидатор контракта — одна точка входа ко всем моделям сразу.

Новых определений здесь нет и быть не должно.
"""

from app.core.audit import AuditLog
from app.core.database import Base
from app.modules.admin.models import IntegrationSetting
from app.modules.auth.models import User
from app.modules.cash.models import CashDesk, MoneyExpense, MoneyIncome
from app.modules.catalog.models import (
    ExpenseCategory,
    ExpenseType,
    Product,
    Unit,
    Warehouse,
)
from app.modules.documents.models import (
    Acquisition,
    AcquisitionItem,
    Notification,
    NotificationItem,
    Transfer,
    TransferItem,
)
from app.modules.issuance.models import (
    Request,
    RequestItem,
    SignatureBatch,
    Writeoff,
    WriteoffItem,
)
from app.modules.stock.models import StockBalance, StockMovement

__all__ = [
    "Base",
    # М1. Справочники (6)
    "User",
    "Unit",
    "Product",
    "Warehouse",
    "ExpenseType",
    "ExpenseCategory",
    # М2. Документооборот товаров (6)
    "Notification",
    "NotificationItem",
    "Acquisition",
    "AcquisitionItem",
    "Transfer",
    "TransferItem",
    # М3. Ядро учёта (2)
    "StockMovement",
    "StockBalance",
    # М4. Заявки и проводки (5, +SignatureBatch — фича 13)
    "Writeoff",
    "WriteoffItem",
    "Request",
    "RequestItem",
    "SignatureBatch",
    # М5. Кассы и деньги (3)
    "CashDesk",
    "MoneyIncome",
    "MoneyExpense",
    # М7. Аудит + Администрирование (2, +IntegrationSetting — спека15)
    "AuditLog",
    "IntegrationSetting",
]

# 6 + 6 + 2 + 5 + 3 + 2 = 24 таблицы (фича 13 добавила signature_batches,
# спека15 добавила integration_settings) — ровно столько, сколько в
# 02-contract.json.
