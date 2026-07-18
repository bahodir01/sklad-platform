"""М1. Справочники: units, products, warehouses, expense_types, expense_categories.

Модели перенесены из 02-database.md §6. Имена таблиц/атрибутов — дословно
из 02-contract.json.

SV-8: физического удаления нет ни у одной из этих сущностей — только
status='archived' / is_active=false. Все FK на справочники — ondelete=RESTRICT.
"""

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.enums import CatalogStatus


class Unit(Base):
    """Единицы измерения: шт, кг, л, м (ТЗ §3.1)."""

    __tablename__ = "units"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # У units нет status: контракт даёт is_active (архивация = is_active=false).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class Product(Base):
    """Номенклатура. Единица измерения хранится ТОЛЬКО здесь: в строках
    документов её нет (3NF, ТЗ §3 — транзитивная зависимость)."""

    __tablename__ = "products"
    __table_args__ = (Index("ix_products_status", "status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units.id", ondelete="RESTRICT"),  # SV-8
        nullable=False,
        index=True,
    )
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[CatalogStatus] = mapped_column(
        SAEnum(CatalogStatus, name="catalog_status"),
        nullable=False,
        server_default=text("'active'"),
    )

    unit: Mapped["Unit"] = relationship()


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (Index("ix_warehouses_status", "status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # SV-9 / ОВ-5: «Склад списания». Заявку сотрудник может подать только сюда;
    # порча/брак, приобретения и перемещения работают с ЛЮБЫМ складом.
    # Отмеченных складов может быть несколько → никакого unique/partial-unique.
    # Правило принудительно проверяет триггер requests_check_issuance_warehouse.
    allows_issuance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[CatalogStatus] = mapped_column(
        SAEnum(CatalogStatus, name="catalog_status"),
        nullable=False,
        server_default=text("'active'"),
    )


class ExpenseType(Base):
    """Тип расхода ТОВАРА: Выдача сотруднику / Порча / Брак.
    НЕ путать с ExpenseCategory (расход ДЕНЕГ)."""

    __tablename__ = "expense_types"
    __table_args__ = (
        # INV-4: целевой ключ составного FK из writeoffs (02-database.md §7.2)
        UniqueConstraint(
            "id", "requires_employee", name="uq_expense_types_id_requires_employee"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    requires_employee: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[CatalogStatus] = mapped_column(
        SAEnum(CatalogStatus, name="catalog_status"),
        nullable=False,
        server_default=text("'active'"),
    )


class ExpenseCategory(Base):
    """Вид расхода ДЕНЕГ: Канцелярия, Хознужды. НЕ путать с ExpenseType."""

    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[CatalogStatus] = mapped_column(
        SAEnum(CatalogStatus, name="catalog_status"),
        nullable=False,
        server_default=text("'active'"),
    )
