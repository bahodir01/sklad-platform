"""М3. Ядро учёта: stock_movements (источник правды) + stock_balances (проекция).

Модели перенесены из 02-database.md §6.

ЭТАП 1: только модели. ledger.py — этап 2 и критический путь всей системы
(архитектура §11): он единственный, кому разрешено писать в эти две таблицы (SV-2).
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import MovementDocType


class StockMovement(Base):
    """Журнал движений — append-only, ЕДИНСТВЕННЫЙ источник правды (ADR-1).
    Записи никогда не редактируются и не удаляются. Пишет только ledger.post()."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        # qty знаковое → CHECK (qty > 0) НЕВОЗМОЖЕН, в отличие от *_items.
        # INV-6 к журналу не относится. Не «чинить» это на > 0 (02-database.md, О-6).
        CheckConstraint("qty <> 0", name="ck_stock_movements_qty_non_zero"),
        # AP-5: keyset-пагинация по (created_at, id); id в хвосте — тай-брейк курсора
        Index(
            "ix_stock_movements_product_wh_created",
            "product_id",
            "warehouse_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_stock_movements_wh_created",
            "warehouse_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        Index("ix_stock_movements_doc", "doc_type", "doc_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)  # ± со знаком
    doc_type: Mapped[MovementDocType] = mapped_column(
        SAEnum(MovementDocType, name="movement_doc_type"), nullable=False
    )
    # Д-3: полиморфная ссылка на документ-основание, FK намеренно нет.
    # Целостность обеспечивает единая точка записи ledger.post() (SV-2).
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StockBalance(Base):
    """Проекция журнала (ADR-1, AP-1). Прямое редактирование запрещено (SV-2):
    единственный писатель — ledger.post() под SELECT ... FOR UPDATE."""

    __tablename__ = "stock_balances"
    __table_args__ = (
        CheckConstraint("qty >= 0", name="ck_stock_balances_qty_non_negative"),  # INV-1
        UniqueConstraint(  # AP-1: точечный поиск + FOR UPDATE
            "product_id", "warehouse_id", name="uq_stock_balances_product_warehouse"
        ),
        Index(  # AP-10: отчёт «остатки по складам», обход склад → товар
            "ix_stock_balances_warehouse_product", "warehouse_id", "product_id"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default=text("0")
    )
    # qty_reserved НЕ добавляем: резервирование вне scope (ТЗ §8, ADR-3).
