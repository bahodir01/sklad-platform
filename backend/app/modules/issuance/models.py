"""М4. Заявка (документ-основание) и расход товара (проводка) — ADR-2.

Модели перенесены из 02-database.md §6.

ADR-2: requests и writeoffs — ДВЕ отдельные таблицы, связанные
requests.writeoff_id, который заполняется ТОЛЬКО в момент выдачи.
До нажатия «Выдано» строки в writeoffs не существует.

ЭТАП 1: только модели. Статусная машина, issue() и ledger — этап 3 (ТЗ §11).
Порядок операций в issue() описан в 02-database.md §7.1 — читать до этапа 3:
предписанный в 03-architecture.md §5.3 порядок нарушает INV-2 на первом же
операторе (CHECK в PostgreSQL немедленный и не может быть DEFERRABLE).
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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
from app.shared.enums import RequestStatus


class Writeoff(Base):
    """Расход товара: выдача сотруднику, порча, брак. Проводка, не заявка.
    Своя, независимая от requests серия номеров (порча/брак заявки не имеют)."""

    __tablename__ = "writeoffs"
    __table_args__ = (
        # INV-4, часть 1: копия флага физически не может разойтись со
        # справочником — ON UPDATE CASCADE протянет изменение в проводки.
        ForeignKeyConstraint(
            ["expense_type_id", "requires_employee"],
            ["expense_types.id", "expense_types.requires_employee"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
            name="fk_writeoffs_expense_type",
        ),
        # INV-4, часть 2: правило стало локальным для строки → обычный CHECK.
        # «Выдача» ⇒ сотрудник обязателен; «Порча»/«Брак» ⇒ сотрудник запрещён.
        CheckConstraint(
            "(employee_id IS NOT NULL) = requires_employee",
            name="ck_writeoffs_employee_iff_required",
        ),
        Index("ix_writeoffs_expense_type_id", "expense_type_id"),
        Index("ix_writeoffs_date", text("date DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    expense_type_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Д-2: копия expense_types.requires_employee. Ставит сервис из выбранного
    # типа расхода; клиент это поле не присылает (api.create = false).
    requires_employee: Mapped[bool] = mapped_column(Boolean, nullable=False)
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    expense_type: Mapped["ExpenseType"] = relationship(  # noqa: F821
        foreign_keys=[expense_type_id],
        primaryjoin="Writeoff.expense_type_id == ExpenseType.id",
        viewonly=True,
    )
    employee: Mapped["User | None"] = relationship(foreign_keys=[employee_id])  # noqa: F821
    author: Mapped["User"] = relationship(foreign_keys=[author_id])  # noqa: F821
    items: Mapped[list["WriteoffItem"]] = relationship(
        back_populates="writeoff", cascade="all, delete-orphan"
    )


class WriteoffItem(Base):
    __tablename__ = "writeoff_items"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_writeoff_items_qty_positive"),  # INV-6
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    writeoff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("writeoffs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    writeoff: Mapped["Writeoff"] = relationship(back_populates="items")


class SignatureBatch(Base):
    """Пачка печати/подписи заявок (фича 13, спека §3). Только для товара.

    Админ на экране «К подписи» выбирает выданные заявки → создаётся пачка,
    им проставляется batch_id и печатается ОДИН PDF, сгруппированный по
    сотрудникам. Печать статус заявки не меняет (признак «напечатано» =
    batch_id IS NOT NULL). «Пачка подписана» переводит issued → signed.
    """

    __tablename__ = "signature_batches"
    __table_args__ = (
        # Период пачки: начало не позже конца. В спеке §3 не задан явно, но
        # период from > to бессмысленен — ставим последний рубеж в БД.
        CheckConstraint(
            "period_from <= period_to", name="ck_signature_batches_period_order"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Серверная серия номеров, как у прочих документов (спека §7).
    number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    period_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_to: Mapped[dt.date] = mapped_column(Date, nullable=False)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    printed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # MinIO
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Request(Base):
    """Заявка сотрудника на получение товара — документ-основание (ADR-2)."""

    __tablename__ = "requests"
    __table_args__ = (
        CheckConstraint("length(trim(reason)) > 0", name="ck_requests_reason_not_blank"),
        # INV-2 — ГЛАВНАЯ защита модели ADR-2 (обновлена фичей 13, спека §2):
        # проводка есть на issued/signed/submitted, т.е. «выдана-и-дальше ⟺
        # есть проводка». Списание рождает writeoff на to_issue → issued.
        CheckConstraint(
            "(status IN ('issued','signed','submitted')) = (writeoff_id IS NOT NULL)",
            name="ck_requests_issued_iff_posted",
        ),
        # INV-3: одна проводка не принадлежит двум заявкам.
        # Заодно покрывает AP-11 (проводка → заявка → бумага): отдельный
        # индекс по writeoff_id не создаём, это был бы дубль B-tree.
        UniqueConstraint("writeoff_id", name="uq_requests_writeoff_id"),
        # AP-4: «мои заявки»
        Index("ix_requests_employee_created", "employee_id", text("created_at DESC")),
        Index("ix_requests_warehouse_id", "warehouse_id"),
        # Фильтр-карточки экрана «Выдачи товара» (спека §5): К выдаче/К подписи/
        # Подписано/Передано = четыре значения status. Один b-tree по status
        # обслуживает все четыре COUNT-а — прежний частичный ix_requests_to_print
        # (одна очередь) снят миграцией 0002 вместе со значением to_print.
        Index("ix_requests_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # ADR-2a: именно этот номер печатается на бумажном бланке
    number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # SV-9: склад выдачи обязан иметь allows_issuance = true НА МОМЕНТ ПОДАЧИ.
    # Проверяет триггер requests_check_issuance_warehouse (BEFORE INSERT OR
    # UPDATE OF warehouse_id) — не составной FK: FK запретил бы админу когда-либо
    # снять галочку со склада, у которого есть исторические заявки.
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        SAEnum(RequestStatus, name="request_status"),
        nullable=False,
        server_default=text("'draft'"),
    )
    printed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    issued_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # ADR-2: NULL до выдачи.
    writeoff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("writeoffs.id", ondelete="RESTRICT"), nullable=True
    )
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # MinIO
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # ── Фича 13 (спека §3): пачка печати/подписи ──
    # Признак «напечатано» = batch_id IS NOT NULL. RESTRICT: пачку с заявками
    # нельзя удалить, не отвязав заявки. Ставит сервер (пакетная печать).
    batch_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("signature_batches.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # ── Фича 13 (спека §4): передача в бухгалтерию ──
    # bulk-действие signed → submitted; один submitted_register_no на пачку
    # передачи. Ставит сервер, клиент не присылает.
    submitted_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    submitted_register_no: Mapped[str | None] = mapped_column(String(32), nullable=True)

    writeoff: Mapped["Writeoff | None"] = relationship()
    batch: Mapped["SignatureBatch | None"] = relationship()
    items: Mapped[list["RequestItem"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class RequestItem(Base):
    __tablename__ = "request_items"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_request_items_qty_positive"),  # INV-6
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)

    request: Mapped["Request"] = relationship(back_populates="items")
