"""М5 «Кассы и деньги» — приход/расход (INV-7, INV-8/ОВ-2, SV-6, §5.4).

Formalises verify_stage45.py scenarios t4-t10 (этап 5). Covers the two items
architecture §9 calls mandatory: касса в минус (single + concurrent).
"""

import asyncio
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.core.exceptions import InsufficientFunds, ValidationError
from app.modules.auth.models import User
from app.modules.cash.models import CashDesk
from app.modules.cash.schemas import MoneyExpenseSubmission, MoneyIncomeCreate
from app.modules.cash.service import CashService
from app.shared.pagination import PageParams
from tests import constants as c

# `expense_category` and `worker_user` fixtures live in conftest.py — shared
# with tests/test_reports.py, which needs the same test-prefixed rows.

TODAY = dt.date.today()
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-receipt-body" * 4  # валиден по magic bytes


async def _desk_balance(session, desk_id: int) -> Decimal:
    d = await session.get(CashDesk, desk_id)
    await session.refresh(d)
    return d.balance


async def _get_user(session, uid: int) -> User:
    return await session.scalar(select(User).where(User.id == uid))


async def test_income_credits_desk_balance(session):
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER,
                amount=Decimal("1000000"),
                date=TODAY,
                comment="пополнение",
            ),
        )
    assert await _desk_balance(session, c.CASH_DESK_TEACHER) == Decimal("1000000.00")


async def test_expense_ok_debits_desk_and_stores_receipt(session, expense_category):
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("1000000"), date=TODAY
            ),
        )
    async with SessionLocal() as s:
        user = await _get_user(s, c.TEACHER_ID)
        exp = await CashService(s).create_expense(
            user=user,
            payload=MoneyExpenseSubmission(
                expense_category_id=expense_category,
                amount=Decimal("300000"),
                description="бумага для принтера",
                date=TODAY,
            ),
            receipt_bytes=PNG,
        )
    assert await _desk_balance(session, c.CASH_DESK_TEACHER) == Decimal("700000.00")
    assert exp.cash_desk_id == c.CASH_DESK_TEACHER
    assert exp.receipt_url


async def test_expense_insufficient_funds_leaves_balance_intact(session, expense_category):
    """INV-8/ОВ-2 жёсткая блокировка: расход сверх баланса → InsufficientFunds,
    баланс не тронут, money_expense не создан."""
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("700000"), date=TODAY
            ),
        )

    with pytest.raises(InsufficientFunds):
        async with SessionLocal() as s:
            user = await _get_user(s, c.TEACHER_ID)
            await CashService(s).create_expense(
                user=user,
                payload=MoneyExpenseSubmission(
                    expense_category_id=expense_category,
                    amount=Decimal("800000"),
                    description="перебор",
                    date=TODAY,
                ),
                receipt_bytes=PNG,
            )

    assert await _desk_balance(session, c.CASH_DESK_TEACHER) == Decimal("700000.00")
    row = await session.execute(text("SELECT count(*) FROM money_expense"))
    assert row.scalar_one() == 0


async def test_expense_without_receipt_rejected_inv7(session, expense_category):
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("100000"), date=TODAY
            ),
        )
    before = await _desk_balance(session, c.CASH_DESK_TEACHER)

    with pytest.raises(ValidationError) as exc_info:
        async with SessionLocal() as s:
            user = await _get_user(s, c.TEACHER_ID)
            await CashService(s).create_expense(
                user=user,
                payload=MoneyExpenseSubmission(
                    expense_category_id=expense_category,
                    amount=Decimal("1000"),
                    description="без чека",
                    date=TODAY,
                ),
                receipt_bytes=b"",
            )
    assert exc_info.value.code == "receipt_required"
    assert await _desk_balance(session, c.CASH_DESK_TEACHER) == before


async def test_expense_bad_receipt_type_rejected(session, expense_category):
    """INV-7 + ТЗ §7: whitelist jpg/png/pdf ПО СОДЕРЖИМОМУ, не по расширению."""
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("100000"), date=TODAY
            ),
        )
    with pytest.raises(ValidationError) as exc_info:
        async with SessionLocal() as s:
            user = await _get_user(s, c.TEACHER_ID)
            await CashService(s).create_expense(
                user=user,
                payload=MoneyExpenseSubmission(
                    expense_category_id=expense_category,
                    amount=Decimal("1000"),
                    description="поддельный чек",
                    date=TODAY,
                ),
                receipt_bytes=b"not-a-real-image-just-text-pretending-to-be-one",
            )
    assert exc_info.value.code == "receipt_bad_type"


async def test_expense_desk_is_server_determined_sv6(session, expense_category, worker_user):
    """SV-6: учитель не может выбрать кассу — MoneyExpenseSubmission
    физически не содержит cash_desk_id. Расход учителя обязан лечь на
    кассу teacher, касса worker должна остаться нетронутой."""
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("100000"), date=TODAY
            ),
        )
    worker_before = await _desk_balance(session, c.CASH_DESK_WORKER)

    async with SessionLocal() as s:
        user = await _get_user(s, c.TEACHER_ID)
        exp = await CashService(s).create_expense(
            user=user,
            payload=MoneyExpenseSubmission(
                expense_category_id=expense_category,
                amount=Decimal("50000"),
                description="SV-6 проверка",
                date=TODAY,
            ),
            receipt_bytes=PNG,
        )

    assert exp.cash_desk_id == c.CASH_DESK_TEACHER
    assert await _desk_balance(session, c.CASH_DESK_WORKER) == worker_before


async def test_admin_cannot_create_own_expense(session, expense_category):
    """SV-6 edge case: admin.category IS NULL (INV-9) — нет своей кассы,
    расход из кассы сотрудника недоступен администратору."""
    from app.core.exceptions import ForbiddenError

    with pytest.raises(ForbiddenError):
        async with SessionLocal() as s:
            admin = await _get_user(s, c.ADMIN_ID)
            await CashService(s).create_expense(
                user=admin,
                payload=MoneyExpenseSubmission(
                    expense_category_id=expense_category,
                    amount=Decimal("1"),
                    description="admin не имеет кассы",
                    date=TODAY,
                ),
                receipt_bytes=PNG,
            )


async def test_concurrent_expenses_do_not_overdraw_desk(session, new_session, expense_category):
    """ГЛАВНЫЙ ТЕСТ INV-8: два параллельных расхода по 400000 при балансе
    700000. FOR UPDATE на cash_desks должен сериализовать их — ровно один
    проходит, второй ловит InsufficientFunds, баланс никогда не уходит в
    минус ни на каком промежуточном шаге."""
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("700000"), date=TODAY
            ),
        )

    async def spend(tag: str) -> str:
        async with new_session() as s:
            user = await _get_user(s, c.TEACHER_ID)
            try:
                await CashService(s).create_expense(
                    user=user,
                    payload=MoneyExpenseSubmission(
                        expense_category_id=expense_category,
                        amount=Decimal("400000"),
                        description=f"гонка {tag}",
                        date=TODAY,
                    ),
                    receipt_bytes=PNG,
                )
                return "ok"
            except InsufficientFunds:
                return "insufficient"

    results = await asyncio.gather(spend("A"), spend("B"))

    assert sorted(results) == ["insufficient", "ok"], f"получили {results}"
    balance = await _desk_balance(session, c.CASH_DESK_TEACHER)
    assert balance == Decimal("300000.00")  # 700000 − ровно одно списание 400000
    assert balance >= Decimal("0")  # INV-8: никогда не в минус


async def test_list_my_expenses_is_row_level_scoped(session, expense_category, worker_user):
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("100000"), date=TODAY
            ),
        )
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_WORKER, amount=Decimal("100000"), date=TODAY
            ),
        )
    async with SessionLocal() as s:
        teacher = await _get_user(s, c.TEACHER_ID)
        await CashService(s).create_expense(
            user=teacher,
            payload=MoneyExpenseSubmission(
                expense_category_id=expense_category,
                amount=Decimal("1000"),
                description="учитель",
                date=TODAY,
            ),
            receipt_bytes=PNG,
        )
    async with SessionLocal() as s:
        worker = await _get_user(s, worker_user)
        await CashService(s).create_expense(
            user=worker,
            payload=MoneyExpenseSubmission(
                expense_category_id=expense_category,
                amount=Decimal("2000"),
                description="работник",
                date=TODAY,
            ),
            receipt_bytes=PNG,
        )

    async with SessionLocal() as s:
        mine, total = await CashService(s).list_my_expenses(
            PageParams(page=1, size=50), employee_id=c.TEACHER_ID
        )

    assert total == 1
    assert all(e.employee_id == c.TEACHER_ID for e in mine)


async def _make_expense(amount: str, expense_category: int) -> int:
    """Проведённый расход учителя → возвращает id (ещё не переданный)."""
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("1000000"), date=TODAY
            ),
        )
    async with SessionLocal() as s:
        user = await _get_user(s, c.TEACHER_ID)
        exp = await CashService(s).create_expense(
            user=user,
            payload=MoneyExpenseSubmission(
                expense_category_id=expense_category,
                amount=Decimal(amount),
                description="расход к передаче",
                date=TODAY,
            ),
            receipt_bytes=PNG,
        )
        return exp.id


async def test_expense_submit_to_accounting_and_filter(session, expense_category):
    """Спека13 §4: расход → submit-to-accounting → submitted_at + register_no;
    фильтр submitted=false его больше не показывает, submitted=true показывает.
    У денег НЕТ этапа подписи — расход готов к передаче сразу после проведения."""
    eid = await _make_expense("300000", expense_category)

    # До передачи: в «Не передано», не в «Передано».
    async with SessionLocal() as s:
        not_sub, n_total = await CashService(s).list_expenses(
            PageParams(page=1, size=50), submitted=False
        )
        sub, s_total = await CashService(s).list_expenses(
            PageParams(page=1, size=50), submitted=True
        )
    assert eid in [e.id for e in not_sub] and n_total == 1
    assert s_total == 0

    # Передача пачкой.
    async with SessionLocal() as s:
        register_no, submitted, skipped = await CashService(s).submit_to_accounting(
            ids=[eid]
        )
    assert submitted == [eid] and skipped == []
    assert register_no and register_no.startswith("MREG-")

    row = await session.execute(
        text("SELECT submitted_at, submitted_register_no FROM money_expense WHERE id=:i"),
        {"i": eid},
    )
    submitted_at, reg = row.first()
    assert submitted_at == TODAY
    assert reg == register_no

    # После передачи: фильтр submitted=false НЕ показывает, submitted=true показывает.
    async with SessionLocal() as s:
        not_sub2, n2 = await CashService(s).list_expenses(
            PageParams(page=1, size=50), submitted=False
        )
        sub2, s2 = await CashService(s).list_expenses(
            PageParams(page=1, size=50), submitted=True
        )
        reg_rows, reg_total = await CashService(s).registry(
            PageParams(page=1, size=50), register_no=register_no
        )
    assert eid not in [e.id for e in not_sub2] and n2 == 0
    assert eid in [e.id for e in sub2] and s2 == 1
    assert reg_total == 1 and reg_rows[0].id == eid


async def test_expense_double_submit_is_idempotent(session, expense_category):
    """Повторная передача уже переданного расхода → skipped, номер реестра не
    перезаписан (условие submitted_at IS NULL в UPDATE)."""
    eid = await _make_expense("100000", expense_category)
    async with SessionLocal() as s:
        first_reg, submitted, _ = await CashService(s).submit_to_accounting(ids=[eid])
    assert submitted == [eid]

    async with SessionLocal() as s:
        second_reg, submitted2, skipped2 = await CashService(s).submit_to_accounting(
            ids=[eid]
        )
    assert submitted2 == [] and skipped2 == [eid]

    row = await session.execute(
        text("SELECT submitted_register_no FROM money_expense WHERE id=:i"), {"i": eid}
    )
    assert row.scalar_one() == first_reg  # номер НЕ перезаписан повторной передачей


async def test_cash_desks_balance_check_enforced_at_db_level(session):
    """INV-8 последний рубеж: CHECK (balance >= 0) на cash_desks не
    зависит от сервисного слоя — прямой UPDATE в минус тоже отклоняется."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        async with SessionLocal() as s:
            await s.execute(
                text("UPDATE cash_desks SET balance = -1 WHERE id = :i"),
                {"i": c.CASH_DESK_TEACHER},
            )
            await s.commit()

    assert await _desk_balance(session, c.CASH_DESK_TEACHER) == Decimal("0.00")
