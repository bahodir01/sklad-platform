"""Pydantic v2-схемы М5. Состав каждой схемы задают API-флаги 02-contract.json,
ДОСЛОВНО (правило то же, что в catalog/issuance: поле ∈ XxxCreate ⟺ api.create,
∈ XxxRead ⟺ api.get_single, ∈ XxxList ⟺ api.get_index).

Карта флагов (перенос из контракта):

  cash_desks     List (get_index):  id type balance
                 Read (get_single): id type balance   (совпадает → наследуем)
                 Create/Update: — (ровно две seed-строки, через API не создаются)

  money_income   List:   id cash_desk_id amount date author_id
                 Read:   + comment
                 Create: cash_desk_id amount date comment
                         (author_id — сервер из JWT; api.create=false)

  money_expense  List:   id cash_desk_id employee_id expense_category_id amount date
                 Read:   + description receipt_url
                 Create: expense_category_id amount description receipt_url date
                         cash_desk_id — СЕРВЕР из users.category (SV-6, api.create=false)
                         employee_id  — СЕРВЕР из JWT (api.create=false)
                         receipt_url  — СЕРВЕР из загруженного файла (multipart)

ПОЧЕМУ НЕТ `MoneyExpenseCreate`. Расход денег — это multipart-запрос: поля формы
плюс ФАЙЛ чека (receipt_url в контракте помечен api.create=true, но физически
приходит файлом, а не строкой-ключом — ключ вычисляет сервер после загрузки в
MinIO). Единой JSON-схемы тела здесь нет; входные поля объявлены как Form()/File()
в роутере, а бизнес-валидация суммы/описания — в модели `MoneyExpenseSubmission`
ниже (имя без суффикса Create/Read/List → вне проверки контракта намеренно: это
не проекция таблицы, а конверт multipart-полей).
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import CashDeskType

# ── cash_desks ──────────────────────────────────────────────────────


class CashDeskList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: CashDeskType
    balance: Decimal


class CashDeskRead(CashDeskList):
    """get_single-состав совпадает с get_index — наследуем, а не копируем."""


# ── money_income ────────────────────────────────────────────────────


class MoneyIncomeCreate(BaseModel):
    """POST /cash/income — только admin (ТЗ §7.2).

    author_id не принимается (api.create=false): сервер ставит его из JWT.
    """

    cash_desk_id: int
    amount: Decimal = Field(gt=0, description="Сумма пополнения, UZS, > 0")
    date: dt.date
    comment: str | None = Field(default=None, max_length=500)


class MoneyIncomeList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cash_desk_id: int
    amount: Decimal
    date: dt.date
    author_id: int


class MoneyIncomeRead(MoneyIncomeList):
    comment: str | None


# ── money_expense ───────────────────────────────────────────────────


class MoneyExpenseList(BaseModel):
    """get_index-состав. description и receipt_url здесь НЕТ (api.get_index=false)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cash_desk_id: int
    employee_id: int
    expense_category_id: int
    amount: Decimal
    date: dt.date


class MoneyExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cash_desk_id: int
    employee_id: int
    expense_category_id: int
    amount: Decimal
    description: str
    receipt_url: str
    date: dt.date


# ── multipart-конверт расхода (вне проверки контракта: нет суффикса) ──


class MoneyExpenseSubmission(BaseModel):
    """Поля-тела формы POST /cash/expenses (без файла чека — он идёт File()).

    cash_desk_id и employee_id СОЗНАТЕЛЬНО отсутствуют: кассу определяет сервер
    из users.category (SV-6), сотрудника — из JWT. Принять их с клиента значило бы
    позволить учителю списать из кассы работников, подделав тело запроса.
    """

    expense_category_id: int
    amount: Decimal = Field(gt=0, description="Сумма расхода, UZS, > 0")
    description: str = Field(min_length=1, description="На что потрачено (непустое)")
    date: dt.date
