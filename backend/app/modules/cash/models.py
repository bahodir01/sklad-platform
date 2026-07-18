"""М5. Кассы и деньги: cash_desks, money_income, money_expense.

Модели перенесены из 02-database.md §6.

ЭТАП 1: только модели + seed двух касс. Сервисы и роутеры — этап 5 (ТЗ §11).

ОВ-2 ЗАКРЫТ заказчиком 17.07.2026: жёсткая блокировка. CHECK (balance >= 0)
живёт в БД и приложением не обходится. Флага CASH_OVERDRAFT_MODE в системе
НЕТ и быть не должно — см. 02-database.md §7.4.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import CashDeskType


class CashDesk(Base):
    """Ровно ДВЕ строки (teacher, worker) — seed-данные начальной миграции.
    Через API кассы не создаются и не удаляются: type UNIQUE это и закрепляет."""

    __tablename__ = "cash_desks"
    __table_args__ = (
        # INV-8 / ОВ-2: жёсткая блокировка ухода баланса в минус
        CheckConstraint("balance >= 0", name="ck_cash_desks_balance_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[CashDeskType] = mapped_column(
        SAEnum(CashDeskType, name="cash_desk_type"), nullable=False, unique=True
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )


class MoneyIncome(Base):
    """Приход денег. Только admin (ТЗ §7.2)."""

    __tablename__ = "money_income"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_money_income_amount_positive"),
        Index("ix_money_income_cash_desk_date", "cash_desk_id", text("date DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cash_desk_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cash_desks.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)


class MoneyExpense(Base):
    """Расход денег сотрудником. Чек обязателен (INV-7)."""

    __tablename__ = "money_expense"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_money_expense_amount_positive"),
        CheckConstraint(
            "length(trim(description)) > 0", name="ck_money_expense_description_not_blank"
        ),
        # INV-7: без этого CHECK пустая строка '' обойдёт NOT NULL и чек станет фикцией
        CheckConstraint(
            "length(trim(receipt_url)) > 0", name="ck_money_expense_receipt_not_blank"
        ),
        # AP-8: отчёт ДДС, фильтр по категории обязателен
        Index("ix_money_expense_category_date", "expense_category_id", text("date DESC")),
        Index("ix_money_expense_cash_desk_date", "cash_desk_id", text("date DESC")),
        Index("ix_money_expense_employee_date", "employee_id", text("date DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # SV-6: кассу определяет СЕРВЕР из users.category, клиент её не присылает —
    # иначе учитель спишет из кассы работников, подделав тело запроса.
    cash_desk_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cash_desks.id", ondelete="RESTRICT"), nullable=False
    )
    employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expense_category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    receipt_url: Mapped[str] = mapped_column(String(500), nullable=False)  # INV-7
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
