"""Telegram-бот (спека15 §2-§4, §6) — юнит-проверка бизнес-склейки без
реального Telegram-токена (его нет в этой среде, см. .feature-dev/15d-
telegram-bot.md «Проверка»).

Три уровня проверки, по убыванию прямоты:
  1. Прямой вызов aiogram-хендлеров (``cmd_start``/``on_contact``) с
     дуцк-тайпнутыми фейками ``Message`` (``unittest.mock.AsyncMock`` на
     ``.answer``) + настоящим ``FSMContext``/``MemoryStorage`` — привязка по
     телефону teach1 сквозь ХЕНДЛЕР, не только через ``logic.py``.
  2. Прямой вызов ``app.bot.logic`` — нормализация телефона, поиск
     пользователя, привязка, сборка заявки/расхода — против ЖИВОЙ БД, теми
     же данными, что дал бы диалог бота (задача, п.2, «если mock aiogram
     трудоёмок — тестируй бизнес-функции напрямую»).
  3. ``test_bot_module_imports_without_error`` — модуль бота импортируется
     без ошибок (задача, п.3): aiogram корректно установлен, синтаксис верен.

teach1 (id=4, см. tests/constants.py) не имеет телефона в сиде — тесты сами
проставляют его через ``UsersService.update`` (эквивалент ``PATCH
/users/{id}``, задача прямо разрешает так сделать) и ОТКАТЫВАЮТ его в
``finally`` — сид не меняется постоянно ни для одного теста этого модуля.
"""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app.bot import logic
from app.core.database import SessionLocal
from app.core.exceptions import InsufficientFunds, ValidationError
from app.modules.auth.models import User
from app.modules.auth.schemas import UserUpdate
from app.modules.cash.schemas import MoneyIncomeCreate
from app.modules.cash.service import CashService
from app.modules.issuance.models import Request, RequestItem
from app.modules.users.service import UsersService
from app.shared.enums import RequestStatus, UserCategory, UserRole
from tests import constants as c
from tests.conftest import TEST_PREFIX

TODAY = dt.date.today()
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-receipt-body" * 4  # валиден по magic bytes (storage.py)

TEACH1_PHONE = "+998901112233"
ADMIN_PHONE = "+998901112234"


async def _set_phone(user_id: int, phone: str | None) -> None:
    """``UsersService.update`` — сервисный слой, который вызывает
    ``PATCH /users/{id}`` (роутер здесь не нужен: он лишь добавляет
    ``require_admin`` поверх того же вызова сервиса)."""
    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        await UsersService(s).update(user_id, UserUpdate(phone=phone), actor=actor)


async def _clear_binding(user_id: int) -> None:
    """Откат телефона И telegram_chat_id — сервис users не трогает
    telegram_chat_id (сервисное поле, только бот), поэтому сбрасываем
    напрямую через сессию."""
    async with SessionLocal() as s:
        row = await s.get(User, user_id)
        row.phone = None
        row.telegram_chat_id = None
        await s.commit()


def _fake_message(chat_id: int, *, contact: SimpleNamespace | None = None) -> SimpleNamespace:
    """Дуцк-тайп ``aiogram.types.Message`` — хендлеры трогают только
    ``.chat.id``, ``.from_user.id``, ``.contact``, ``.answer()``."""
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=chat_id),
        contact=contact,
        answer=AsyncMock(),
    )


def _fresh_state(chat_id: int) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id)
    return FSMContext(storage=storage, key=key)


# ══════════════════════ 1. Нормализация телефона (logic.py) ═══════════


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("998901234567", "+998901234567"),  # Telegram обычно шлёт без '+'
        ("+998901234567", "+998901234567"),  # уже нормализован
        ("00998901234567", "+998901234567"),  # международный 00-префикс
        ("+998 90 123-45-67", "+998901234567"),  # пробелы/дефисы
        ("+998 (90) 123 45 67", "+998901234567"),  # скобки
        ("abc", None),  # мусор
        ("", None),  # пусто
        ("+123", None),  # короче 9 цифр после '+'
    ],
)
def test_normalize_phone(raw: str, expected: str | None) -> None:
    assert logic.normalize_phone(raw) == expected


def test_role_label_russian() -> None:
    assert logic.role_label(UserRole.teacher) == "учитель"
    assert logic.role_label(UserRole.worker) == "работник"
    assert logic.role_label(UserRole.admin) == "администратор"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5", Decimal("5")),
        ("5.5", Decimal("5.5")),
        ("5,5", Decimal("5.5")),  # запятая — частый ввод с телефона
        ("0", None),  # не > 0
        ("-3", None),
        ("не число", None),
        ("", None),
    ],
)
def test_parse_positive_decimal(raw: str, expected: Decimal | None) -> None:
    assert logic.parse_positive_decimal(raw) == expected


# ══════════════════════ 2. Привязка через logic.py (живая БД) ═════════


async def test_bind_telegram_account_success(session):
    chat_id = 900_000_001
    await _set_phone(c.TEACHER_ID, TEACH1_PHONE)
    try:
        async with SessionLocal() as s:
            outcome = await logic.bind_telegram_account(
                s, phone_raw="998901112233", chat_id=chat_id  # без '+', как шлёт Telegram
            )
        assert outcome.status == "ok"
        assert outcome.user is not None
        assert outcome.user.id == c.TEACHER_ID
        assert outcome.user.role == UserRole.teacher

        row = await session.get(User, c.TEACHER_ID)
        await session.refresh(row)
        assert row.telegram_chat_id == chat_id
    finally:
        await _clear_binding(c.TEACHER_ID)


async def test_bind_telegram_account_unknown_phone_not_found(session):
    async with SessionLocal() as s:
        outcome = await logic.bind_telegram_account(
            s, phone_raw="+998999999999", chat_id=900_000_002
        )
    assert outcome.status == "not_found"
    assert outcome.user is None


async def test_bind_telegram_account_admin_not_bound(session):
    """Спека15 §2: бот не обслуживает admin — telegram_chat_id НЕ пишется,
    даже если номер найден и принадлежит администратору."""
    chat_id = 900_000_003
    await _set_phone(c.ADMIN_ID, ADMIN_PHONE)
    try:
        async with SessionLocal() as s:
            outcome = await logic.bind_telegram_account(
                s, phone_raw=ADMIN_PHONE, chat_id=chat_id
            )
        assert outcome.status == "ok"
        assert outcome.user.role == UserRole.admin

        row = await session.get(User, c.ADMIN_ID)
        await session.refresh(row)
        assert row.telegram_chat_id is None  # НЕ привязан
    finally:
        await _clear_binding(c.ADMIN_ID)


async def test_bind_telegram_account_inactive_not_bound(session):
    """Спека15 §8: is_active=false → отказ, привязка не пишется."""
    phone = "+998901112299"
    async with SessionLocal() as s:
        inactive = User(
            full_name="Тестовый Неактивный",
            username=f"{TEST_PREFIX}inactive_bot",
            password_hash="x",
            role=UserRole.worker,
            category=UserCategory.worker,
            is_active=False,
            phone=phone,
        )
        s.add(inactive)
        await s.commit()
        await s.refresh(inactive)
        user_id = inactive.id

    chat_id = 900_000_004
    async with SessionLocal() as s:
        outcome = await logic.bind_telegram_account(s, phone_raw=phone, chat_id=chat_id)
    assert outcome.status == "ok"
    assert outcome.user.is_active is False

    async with SessionLocal() as s:
        row = await s.get(User, user_id)
        assert row.telegram_chat_id is None


async def test_bind_telegram_account_chat_taken_by_another_user(session, worker_user):
    """Один Telegram-аккаунт — один пользователь (спека15 §2): второй
    пользователь не может занять уже привязанный chat_id."""
    shared_chat_id = 900_000_005
    await _set_phone(c.TEACHER_ID, TEACH1_PHONE)
    worker_phone = "+998901112255"
    async with SessionLocal() as s:
        worker_row = await s.get(User, worker_user)
        worker_row.phone = worker_phone
        await s.commit()
    try:
        async with SessionLocal() as s:
            first = await logic.bind_telegram_account(
                s, phone_raw=TEACH1_PHONE, chat_id=shared_chat_id
            )
        assert first.status == "ok"

        async with SessionLocal() as s:
            second = await logic.bind_telegram_account(
                s, phone_raw=worker_phone, chat_id=shared_chat_id
            )
        assert second.status == "chat_taken"

        # Первая привязка не пострадала.
        row = await session.get(User, c.TEACHER_ID)
        await session.refresh(row)
        assert row.telegram_chat_id == shared_chat_id
    finally:
        await _clear_binding(c.TEACHER_ID)


# ══════════════════════ 3. Хендлеры aiogram напрямую (фейковый Message) ═


async def test_handler_start_unbound_prompts_phone_button():
    from app.bot.handlers import cmd_start

    chat_id = 900_100_001
    msg = _fake_message(chat_id)
    state = _fresh_state(chat_id)

    await cmd_start(msg, state)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "телефон" in text.lower()


async def test_handler_on_contact_binds_known_phone_and_greets():
    from app.bot.handlers import on_contact

    chat_id = 900_100_002
    await _set_phone(c.TEACHER_ID, TEACH1_PHONE)
    try:
        contact = SimpleNamespace(phone_number="998901112233", user_id=chat_id)
        msg = _fake_message(chat_id, contact=contact)
        state = _fresh_state(chat_id)

        await on_contact(msg, state)

        msg.answer.assert_awaited_once()
        text = msg.answer.await_args.args[0]
        assert "здравствуйте" in text.lower()
        assert "учитель" in text.lower()

        async with SessionLocal() as s:
            row = await s.get(User, c.TEACHER_ID)
            assert row.telegram_chat_id == chat_id
    finally:
        await _clear_binding(c.TEACHER_ID)


async def test_handler_on_contact_unknown_phone_rejected():
    from app.bot.handlers import on_contact

    chat_id = 900_100_003
    contact = SimpleNamespace(phone_number="998999999999", user_id=chat_id)
    msg = _fake_message(chat_id, contact=contact)
    state = _fresh_state(chat_id)

    await on_contact(msg, state)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "не найден" in text.lower()


async def test_handler_on_contact_admin_gets_polite_refusal():
    from app.bot.handlers import on_contact

    chat_id = 900_100_004
    await _set_phone(c.ADMIN_ID, ADMIN_PHONE)
    try:
        contact = SimpleNamespace(phone_number=ADMIN_PHONE.lstrip("+"), user_id=chat_id)
        msg = _fake_message(chat_id, contact=contact)
        state = _fresh_state(chat_id)

        await on_contact(msg, state)

        text = msg.answer.await_args.args[0]
        assert "администратор работает через веб-панель" in text.lower()

        async with SessionLocal() as s:
            row = await s.get(User, c.ADMIN_ID)
            assert row.telegram_chat_id is None
    finally:
        await _clear_binding(c.ADMIN_ID)


# ══════════════════════ 4. Полный цикл заявки на товар (logic.py) ═════


async def test_submit_issuance_request_creates_and_confirms(session):
    """Спека15 §3 шаг 7: create_request + confirm_request → to_issue,
    ОДНА позиция. Проверяем через прямой запрос к БД после вызова."""
    async with SessionLocal() as s:
        request = await logic.submit_issuance_request(
            s,
            employee_id=c.TEACHER_ID,
            warehouse_id=c.WAREHOUSE_ISS,
            product_id=c.PRODUCT_ID,
            qty=Decimal("3"),
            reason="Нужна бумага для урока (бот)",
        )
    assert request.status == RequestStatus.to_issue
    assert request.number.startswith("REQ-")

    row = await session.scalar(select(Request).where(Request.id == request.id))
    assert row is not None
    assert row.employee_id == c.TEACHER_ID
    assert row.warehouse_id == c.WAREHOUSE_ISS
    assert row.status == RequestStatus.to_issue

    items = list(
        await session.scalars(select(RequestItem).where(RequestItem.request_id == request.id))
    )
    assert len(items) == 1
    assert items[0].product_id == c.PRODUCT_ID
    assert items[0].qty == Decimal("3")


async def test_submit_issuance_request_wrong_warehouse_rejected(session):
    """SV-9: склад без allows_issuance=true отклоняется — тот же путь,
    которым прошёл бы диалог, если бы бот дал выбрать неверный склад."""
    with pytest.raises(ValidationError) as exc_info:
        async with SessionLocal() as s:
            await logic.submit_issuance_request(
                s,
                employee_id=c.TEACHER_ID,
                warehouse_id=c.WAREHOUSE_NO,
                product_id=c.PRODUCT_ID,
                qty=Decimal("1"),
                reason="не должно пройти",
            )
    assert exc_info.value.code == "warehouse_not_issuance"


# ══════════════════════ 5. Полный цикл расхода денег (logic.py) ═══════


async def test_submit_cash_expense_creates_and_debits_desk(session, expense_category):
    async with SessionLocal() as s:
        await CashService(s).create_income(
            author_id=c.ADMIN_ID,
            payload=MoneyIncomeCreate(
                cash_desk_id=c.CASH_DESK_TEACHER, amount=Decimal("500000"), date=TODAY
            ),
        )

    async with SessionLocal() as s:
        user = await s.get(User, c.TEACHER_ID)
        expense = await logic.submit_cash_expense(
            s,
            user=user,
            expense_category_id=expense_category,
            amount=Decimal("120000"),
            description="Хозтовары для кабинета (бот)",
            receipt_bytes=PNG,
        )
    assert expense.cash_desk_id == c.CASH_DESK_TEACHER
    assert expense.employee_id == c.TEACHER_ID
    assert expense.receipt_url

    from app.modules.cash.models import CashDesk

    desk = await session.get(CashDesk, c.CASH_DESK_TEACHER)
    await session.refresh(desk)
    assert desk.balance == Decimal("380000.00")


async def test_submit_cash_expense_insufficient_funds(session, expense_category):
    """§4 шаг 6: InsufficientFunds передаётся хендлером текстом как есть —
    здесь проверяем, что сам вызов действительно её поднимает и баланс/чек
    не создаются (файл ещё не сохранён, INSERT не сделан)."""
    async with SessionLocal() as s:
        user = await s.get(User, c.TEACHER_ID)
        with pytest.raises(InsufficientFunds):
            await logic.submit_cash_expense(
                s,
                user=user,
                expense_category_id=expense_category,
                amount=Decimal("999999999"),
                description="слишком много",
                receipt_bytes=PNG,
            )

    from app.modules.cash.models import CashDesk

    desk = await session.get(CashDesk, c.CASH_DESK_TEACHER)
    await session.refresh(desk)
    assert desk.balance == Decimal("0.00")


# ══════════════════════ 6. Модуль импортируется (задача, п.3) ═════════


def test_bot_module_imports_without_error() -> None:
    from app.bot import handlers, keyboards, logic as logic_mod, main, states  # noqa: F401

    assert len(handlers.router.observers) > 0
