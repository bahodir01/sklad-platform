"""Роутер М5 (архитектура §6):
  admin:          POST /cash/income
  teacher/worker: POST /cash/expenses (multipart + чек), GET /cash/expenses/my
  any role:       GET /cash/desks (балансы; нужны и админу для прихода, и
                  сотруднику для формы расхода)

Порядок маршрутов: статический /cash/expenses/my объявлен ДО POST /cash/expenses
и не конфликтует с ним (разные методы и пути). Отдельного /cash/expenses/{id} нет.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import require_admin, require_any_role, require_role
from app.modules.auth.models import User
from app.modules.cash.schemas import (
    CashDeskRead,
    ExpenseRegistryRow,
    ExpenseSubmitRequest,
    ExpenseSubmitResult,
    MoneyExpenseRead,
    MoneyExpenseSubmission,
    MoneyExpenseList,
    MoneyIncomeCreate,
    MoneyIncomeRead,
)
from app.modules.cash.service import CashService
from app.shared.enums import UserRole
from app.shared.pagination import Page, PageParamsDep

router = APIRouter(tags=["cash"])

# Расход денег проводит сотрудник (teacher|worker); admin своей кассы не имеет
# (category IS NULL, INV-9) и деньги тратит не он, а сотрудники (§7.3).
require_employee = require_role(UserRole.teacher, UserRole.worker)


# ══════════════════════ Балансы касс ════════════════════════════════


@router.get(
    "/cash/desks",
    response_model=list[CashDeskRead],
    summary="Балансы касс (teacher/worker), AP-9",
)
async def list_desks(
    _: User = Depends(require_any_role),
    session: AsyncSession = Depends(get_session),
) -> list[CashDeskRead]:
    desks = await CashService(session).list_desks()
    return [CashDeskRead.model_validate(d) for d in desks]


# ══════════════════════ Приход (admin, §7.2) ════════════════════════


@router.post(
    "/cash/income",
    response_model=MoneyIncomeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Пополнить кассу (ТОЛЬКО admin, §7.2)",
)
async def create_income(
    payload: MoneyIncomeCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MoneyIncomeRead:
    # author_id — сервер из current_user (api.create=false).
    income = await CashService(session).create_income(author_id=user.id, payload=payload)
    return MoneyIncomeRead.model_validate(income)


# ══════════════════════ Расход (сотрудник, §5.4) ════════════════════


@router.get(
    "/cash/expenses/my",
    response_model=Page[MoneyExpenseList],
    summary="Мои расходы (row-level: только свои, §1.3)",
)
async def my_expenses(
    params: PageParamsDep,
    user: User = Depends(require_employee),
    session: AsyncSession = Depends(get_session),
) -> Page[MoneyExpenseList]:
    items, total = await CashService(session).list_my_expenses(params, employee_id=user.id)
    return Page.build([MoneyExpenseList.model_validate(i) for i in items], total, params)


@router.get(
    "/cash/expenses/registry",
    response_model=Page[ExpenseRegistryRow],
    summary="Реестр передачи денег в бухгалтерию (admin, спека13 §4)",
)
async def expenses_registry(
    params: PageParamsDep,
    register_no: Annotated[str | None, Query(description="Номер реестра передачи")] = None,
    date: Annotated[str | None, Query(description="Дата передачи YYYY-MM-DD")] = None,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Page[ExpenseRegistryRow]:
    parsed_date = dt.date.fromisoformat(date) if date else None
    items, total = await CashService(session).registry(
        params, register_no=register_no, date=parsed_date
    )
    return Page.build(
        [ExpenseRegistryRow.model_validate(i) for i in items], total, params
    )


@router.post(
    "/cash/expenses/submit-to-accounting",
    response_model=ExpenseSubmitResult,
    summary="Передать расходы в бухгалтерию пачкой (admin, № реестра; спека13 §4)",
)
async def submit_expenses_to_accounting(
    payload: ExpenseSubmitRequest,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ExpenseSubmitResult:
    register_no, submitted, skipped = await CashService(session).submit_to_accounting(
        ids=payload.ids
    )
    return ExpenseSubmitResult(
        register_no=register_no, submitted=submitted, skipped=skipped
    )


@router.get(
    "/cash/expenses",
    response_model=Page[MoneyExpenseList],
    summary="Расходы денег, фильтр «Передано/Не передано» (admin, спека13 §4)",
)
async def list_expenses(
    params: PageParamsDep,
    submitted: Annotated[bool | None, Query(description="true=переданные, false=нет")] = None,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Page[MoneyExpenseList]:
    items, total = await CashService(session).list_expenses(params, submitted=submitted)
    return Page.build([MoneyExpenseList.model_validate(i) for i in items], total, params)


@router.post(
    "/cash/expenses",
    response_model=MoneyExpenseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Провести расход денег с чеком (teacher/worker, §5.4)",
)
async def create_expense(
    expense_category_id: Annotated[int, Form(ge=1)],
    amount: Annotated[Decimal, Form(gt=0, description="Сумма расхода, UZS, > 0")],
    description: Annotated[str, Form(min_length=1)],
    date: Annotated[dt.date, Form()],
    # INV-7: чек ОБЯЗАТЕЛЕН — File(...) без значения по умолчанию делает поле
    # required; без файла FastAPI вернёт 422 ещё до входа в сервис.
    receipt: Annotated[UploadFile, File(description="Чек: jpg/png/pdf, ≤ 10 МБ")],
    user: User = Depends(require_employee),
    session: AsyncSession = Depends(get_session),
) -> MoneyExpenseRead:
    """SV-6: cash_desk_id и employee_id НЕ принимаются с клиента — сервер берёт
    кассу из user.category, сотрудника из JWT. Чек проверяется по magic bytes."""
    payload = MoneyExpenseSubmission(
        expense_category_id=expense_category_id,
        amount=amount,
        description=description,
        date=date,
    )
    receipt_bytes = await receipt.read()
    expense = await CashService(session).create_expense(
        user=user, payload=payload, receipt_bytes=receipt_bytes
    )
    return MoneyExpenseRead.model_validate(expense)
