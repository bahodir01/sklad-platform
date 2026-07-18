"""М2. Документооборот товаров: notifications, acquisitions, transfers (+ строки).

Модели перенесены из 02-database.md §6.

ЭТАП 1: только модели — сервисы и роутеры М2 относятся к этапу 2 (ТЗ §11).
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.enums import NotificationStatus


class Notification(Base):
    """Уведомление в адрес отдела закупки. Одно уведомление → много
    приобретений (закупка частями)."""

    __tablename__ = "notifications"
    __table_args__ = (
        # Тело документа и подразделение печатаются на бланке BILDIRISHNOMA —
        # NOT NULL сам по себе допускает '', пустая строка ушла бы в печать.
        CheckConstraint("length(trim(body_text)) > 0", name="ck_notifications_body_text_not_blank"),
        CheckConstraint(
            "length(trim(division_name)) > 0", name="ck_notifications_division_name_not_blank"
        ),
        Index("ix_notifications_status", "status"),
        Index("ix_notifications_date", text("date DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        SAEnum(NotificationStatus, name="notification_status"),
        nullable=False,
        server_default=text("'draft'"),
    )
    # На бланке BILDIRISHNOMA печатается как «Ehtiyojning asoslanishi».
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ── Печатная форма BILDIRISHNOMA (уточнение заказчика 17.07.2026) ──
    # Абзац-обращение бланка. Товары в него НЕ дублируются — перечень
    # рендерится из notification_items (см. templates/pdf/notification.html).
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    # «Bo‘linma nomi». Свободный текст, НЕ справочник и НЕ FK на warehouses:
    # подразделение («кто просит») и склад назначения («куда придёт товар») —
    # разные сущности (решение заказчика).
    division_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Снимок напечатанного бланка в MinIO. Ставит сервер; печать не меняет
    # status, перепечатка безопасна — на бланке только запрошенное количество.
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list["NotificationItem"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan"
    )


class NotificationItem(Base):
    __tablename__ = "notification_items"
    __table_args__ = (
        CheckConstraint("qty_requested > 0", name="ck_notification_items_qty_positive"),  # INV-6
        # AP-6/AP-7 агрегируют по (notification_id, product_id) — пара обязана
        # быть уникальной, иначе «остаток к приобретению» неоднозначен.
        UniqueConstraint(
            "notification_id",
            "product_id",
            name="uq_notification_items_notification_product",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    qty_requested: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)

    notification: Mapped["Notification"] = relationship(back_populates="items")
    # qty_purchased и «остаток к приобретению» НЕ ХРАНЯТСЯ — считаются
    # из acquisition_items (ТЗ §3). Второй источник правды не заводим.


class Acquisition(Base):
    """Приобретение (частичная закупка). Строго привязано к одному уведомлению."""

    __tablename__ = "acquisitions"
    __table_args__ = (Index("ix_acquisitions_date", text("date DESC")),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    notification_id: Mapped[int] = mapped_column(  # AP-6
        BigInteger,
        ForeignKey("notifications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)  # ОВ-4
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    items: Mapped[list["AcquisitionItem"]] = relationship(
        back_populates="acquisition", cascade="all, delete-orphan"
    )


class AcquisitionItem(Base):
    __tablename__ = "acquisition_items"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_acquisition_items_qty_positive"),  # INV-6
        CheckConstraint(
            "price IS NULL OR price >= 0", name="ck_acquisition_items_price_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    acquisition_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("acquisitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(  # AP-6
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    acquisition: Mapped["Acquisition"] = relationship(back_populates="items")


class Transfer(Base):
    """Перемещение между складами. Порождает ДВЕ записи в stock_movements."""

    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint(  # INV-5
            "from_warehouse_id <> to_warehouse_id", name="ck_transfers_different_warehouses"
        ),
        Index("ix_transfers_date", text("date DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    from_warehouse_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    to_warehouse_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    items: Mapped[list["TransferItem"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan"
    )


class TransferItem(Base):
    __tablename__ = "transfer_items"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_transfer_items_qty_positive"),  # INV-6
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transfer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("transfers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)

    transfer: Mapped["Transfer"] = relationship(back_populates="items")
