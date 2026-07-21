"""Бизнес-склейка Telegram-бота (спека15 §2-§4), без единого импорта aiogram.

Хендлеры (``handlers.py``) — тонкие: разбор апдейта Telegram, вызов функции
отсюда, отрисовка ответа. Всё, что здесь, тестируется НАПРЯМУЮ против живой
БД без mock-объектов aiogram (задача «Проверка», п.2): нормализация
телефона, поиск пользователя по телефону/chat_id, привязка аккаунта, сборка
заявки/расхода через ``IssuanceService``/``CashService`` с данными, которые
дал бы диалог бота.

Бот не дублирует бизнес-правила: заявка идёт через
``IssuanceService.create_request`` + ``confirm_request``, расход — через
``CashService.create_expense`` — те же сервисы, что вызывает HTTP-слой
(ТЗ15 §7: «бот — ещё один клиент API, не отдельный привилегированный путь»).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.cash.models import MoneyExpense
from app.modules.cash.schemas import MoneyExpenseSubmission
from app.modules.cash.service import CashService
from app.modules.catalog.models import ExpenseCategory, Product, Warehouse
from app.modules.issuance.models import Request
from app.modules.issuance.schemas import RequestCreate, RequestItemCreate
from app.modules.issuance.service import IssuanceService
from app.shared.enums import CatalogStatus, UserRole

# спека15 §8 «Открытые мелочи»: привести к E.164 при сохранении. Telegram
# отдаёт contact.phone_number обычно БЕЗ ведущего '+' (напр. "998901234567");
# админ мог ввести с пробелами/скобками/00-префиксом в users.phone — приводим
# оба источника к одному нормализованному виду перед сравнением.
_PHONE_STRIP_RE = re.compile(r"[^\d+]")
_PHONE_VALID_RE = re.compile(r"^\+\d{9,15}$")  # тот же формат, что ck_users_phone_format

ROLE_LABELS_RU: dict[UserRole, str] = {
    UserRole.admin: "администратор",
    UserRole.teacher: "учитель",
    UserRole.worker: "работник",
}


def role_label(role: UserRole) -> str:
    return ROLE_LABELS_RU.get(role, role.value)


def normalize_phone(raw: str) -> str | None:
    """Сырой ввод (Telegram contact ИЛИ ручной набор) → ``^\\+\\d{9,15}$``.

    ``None``, если после очистки формат всё равно не подходит (напр. пустая
    строка, буквы, слишком короткий номер) — вызывающий код трактует это как
    «номер не найден», не роняя диалог.
    """
    if not raw:
        return None
    cleaned = _PHONE_STRIP_RE.sub("", raw.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    elif not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned if _PHONE_VALID_RE.match(cleaned) else None


def parse_positive_decimal(raw: str) -> Decimal | None:
    """Валидация формата НА СТОРОНЕ БОТА (спека15 §3 п.4): число, > 0, до
    отправки на сервер. ``,`` принимается как десятичный разделитель (частый
    ввод на телефоне)."""
    if raw is None:
        return None
    text = raw.strip().replace(",", ".")
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if value <= 0:
        return None
    return value


# ══════════════════════ Привязка аккаунта (спека15 §2) ═══════════════


@dataclass
class BindOutcome:
    """``status``: "ok" (найден и, если можно, привязан — is_active/role
    решает хендлер через ``user``), "not_found" (номер не в системе),
    "chat_taken" (этот Telegram уже привязан к ДРУГОМУ пользователю)."""

    status: str
    user: User | None = None


async def find_user_by_chat_id(session: AsyncSession, chat_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_chat_id == chat_id))


async def find_user_by_phone(session: AsyncSession, phone: str) -> User | None:
    return await session.scalar(select(User).where(User.phone == phone))


async def bind_telegram_account(
    session: AsyncSession, *, phone_raw: str, chat_id: int
) -> BindOutcome:
    """Спека15 §2, шаги 3-5. НЕ пишет ``telegram_chat_id`` для admin или
    ``is_active=false`` — тексты отказа для этих случаев решает вызывающий
    хендлер (``handlers._greet_or_reject``) по ``outcome.user``, привязка
    здесь лишь решает, МОЖНО ли физически записать chat_id."""
    phone = normalize_phone(phone_raw)
    if phone is None:
        return BindOutcome(status="not_found")

    user = await find_user_by_phone(session, phone)
    if user is None:
        return BindOutcome(status="not_found")

    if user.telegram_chat_id == chat_id:
        return BindOutcome(status="ok", user=user)  # уже привязан этим чатом

    if not user.is_active or user.role == UserRole.admin:
        # Бот не обслуживает admin/неактивных — но и не сохраняет попытку,
        # только сообщает отказ (через _greet_or_reject у вызывающего).
        return BindOutcome(status="ok", user=user)

    user.telegram_chat_id = chat_id
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return BindOutcome(status="chat_taken")
    await session.refresh(user)
    return BindOutcome(status="ok", user=user)


# ══════════════════════ Справочники для клавиатур ═════════════════════


async def list_issuance_warehouses(session: AsyncSession) -> list[Warehouse]:
    """SV-9: только склады ``allows_issuance=true`` и активные (§3, шаг 1)."""
    stmt = (
        select(Warehouse)
        .where(Warehouse.allows_issuance.is_(True), Warehouse.status == CatalogStatus.active)
        .order_by(Warehouse.name)
    )
    return list(await session.scalars(stmt))


async def get_warehouse(session: AsyncSession, warehouse_id: int) -> Warehouse | None:
    return await session.get(Warehouse, warehouse_id)


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def list_active_expense_categories(session: AsyncSession) -> list[ExpenseCategory]:
    stmt = (
        select(ExpenseCategory)
        .where(ExpenseCategory.status == CatalogStatus.active)
        .order_by(ExpenseCategory.name)
    )
    return list(await session.scalars(stmt))


async def get_expense_category(session: AsyncSession, category_id: int) -> ExpenseCategory | None:
    return await session.get(ExpenseCategory, category_id)


# ══════════════════════ Создание заявки / расхода ═════════════════════


async def submit_issuance_request(
    session: AsyncSession,
    *,
    employee_id: int,
    warehouse_id: int,
    product_id: int,
    qty: Decimal,
    reason: str,
) -> Request:
    """Спека15 §3, шаг 7: ``POST /requests`` + ``POST /requests/{id}/confirm``
    от имени привязанного пользователя, ОДНА позиция (§3 «Множественные
    строки» — вне scope первой версии бота)."""
    service = IssuanceService(session)
    payload = RequestCreate(
        warehouse_id=warehouse_id,
        reason=reason,
        items=[RequestItemCreate(product_id=product_id, qty=qty)],
    )
    created = await service.create_request(employee_id=employee_id, payload=payload)
    return await service.confirm_request(request_id=created.id, employee_id=employee_id)


async def submit_cash_expense(
    session: AsyncSession,
    *,
    user: User,
    expense_category_id: int,
    amount: Decimal,
    description: str,
    receipt_bytes: bytes,
    date: dt.date | None = None,
) -> MoneyExpense:
    """Спека15 §4, шаг 6: ``CashService.create_expense`` с фото чека,
    скачанным ботом (байты, не HTTP multipart — тот же сервисный вызов, что
    и веб-форма делает после загрузки файла). Касса определяется сервером по
    ``user.category`` (SV-6) — бот её не выбирает и не передаёт."""
    service = CashService(session)
    payload = MoneyExpenseSubmission(
        expense_category_id=expense_category_id,
        amount=amount,
        description=description,
        date=date or dt.date.today(),
    )
    return await service.create_expense(user=user, payload=payload, receipt_bytes=receipt_bytes)
