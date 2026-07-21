"""Диалоги Telegram-бота (спека15 §2-§4): aiogram Router, подключается в
main.py. Хендлеры — тонкие: разбор апдейта → вызов ``app.bot.logic``/
``app.modules.ai.service`` → отрисовка ответа клавиатурой из
``app.bot.keyboards``. Бизнес-правила живут в вызываемых сервисах
(``IssuanceService``/``CashService``/``resolve_product_query``), не здесь.

Каждый хендлер, которому нужна БД, открывает СВОЮ сессию через
``SessionLocal()`` и закрывает её по выходу из ``async with`` — тот же
принцип «один вызов = одна транзакция» (архитектура §2), что и HTTP-слой:
Telegram-апдейт для бота — то же самое, что HTTP-запрос для FastAPI.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import logic
from app.bot.states import ExpenseStates, IssuanceStates
from app.core.database import SessionLocal
from app.core.exceptions import DomainError
from app.modules.ai.service import find_all_paginated, resolve_product_query
from app.modules.auth.models import User
from app.shared.enums import UserRole

logger = logging.getLogger(__name__)
router = Router(name="sklad_bot")

_PRODUCT_PAGE_SIZE = 8

_NOT_FOUND_TEXT = "Ваш номер не найден в системе. Обратитесь к администратору."
_INACTIVE_TEXT = "Ваша учётная запись отключена. Обратитесь к администратору."
_ADMIN_TEXT = (
    "Этот бот предназначен только для сотрудников (учитель/работник). "
    "Администратор работает через веб-панель."
)
_CHAT_TAKEN_TEXT = "Этот Telegram-аккаунт уже привязан к другому пользователю."
_SESSION_EXPIRED_TEXT = "Сессия истекла. Отправьте /start и повторите."


# ══════════════════════ /start и привязка (спека15 §2) ════════════════


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with SessionLocal() as session:
        user = await logic.find_user_by_chat_id(session, message.chat.id)
    if user is None:
        await message.answer(
            "Здравствуйте! Чтобы начать работу, отправьте номер телефона кнопкой ниже.",
            reply_markup=kb.request_phone_keyboard(),
        )
        return
    await _greet_or_reject(message, user)


async def _greet_or_reject(message: Message, user: User) -> None:
    """Общий текст приветствия/отказа — используется и повторным /start, и
    сразу после успешной привязки (спека15 §2, шаги 3 и 5)."""
    if not user.is_active:
        await message.answer(_INACTIVE_TEXT, reply_markup=kb.remove_keyboard())
        return
    if user.role == UserRole.admin:
        await message.answer(_ADMIN_TEXT, reply_markup=kb.remove_keyboard())
        return
    await message.answer(
        f"Здравствуйте, {user.full_name}, вы авторизованы как {logic.role_label(user.role)}.",
        reply_markup=kb.main_menu_keyboard(),
    )


@router.message(F.contact)
async def on_contact(message: Message, state: FSMContext) -> None:
    await state.clear()
    contact = message.contact
    if contact.user_id is not None and message.from_user is not None and contact.user_id != message.from_user.id:
        # Пересланный чужой контакт — не подтверждение личности отправителя.
        await message.answer(
            "Пожалуйста, отправьте СВОЙ номер телефона кнопкой ниже.",
            reply_markup=kb.request_phone_keyboard(),
        )
        return

    async with SessionLocal() as session:
        outcome = await logic.bind_telegram_account(
            session, phone_raw=contact.phone_number, chat_id=message.chat.id
        )

    if outcome.status == "not_found":
        await message.answer(_NOT_FOUND_TEXT, reply_markup=kb.request_phone_keyboard())
        return
    if outcome.status == "chat_taken":
        await message.answer(_CHAT_TAKEN_TEXT, reply_markup=kb.remove_keyboard())
        return
    await _greet_or_reject(message, outcome.user)  # type: ignore[arg-type]


async def _require_employee(message: Message) -> User | None:
    """Общий guard перед любым действием в меню: привязан, активен, не
    admin. Сам отвечает отказом и возвращает ``None``, если что-то не так —
    вызывающий хендлер просто делает ``return``."""
    async with SessionLocal() as session:
        user = await logic.find_user_by_chat_id(session, message.chat.id)
    if user is None:
        await message.answer(
            "Сначала привяжите аккаунт: отправьте /start.",
            reply_markup=kb.request_phone_keyboard(),
        )
        return None
    if not user.is_active:
        await message.answer(_INACTIVE_TEXT, reply_markup=kb.remove_keyboard())
        return None
    if user.role == UserRole.admin:
        await message.answer(_ADMIN_TEXT, reply_markup=kb.remove_keyboard())
        return None
    return user


# ══════════════════════ Главное меню ═══════════════════════════════════


@router.message(F.text == kb.BTN_MENU_ISSUANCE)
async def menu_issuance(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await _require_employee(message)
    if user is None:
        return
    async with SessionLocal() as session:
        warehouses = await logic.list_issuance_warehouses(session)
    if not warehouses:
        await message.answer("Нет складов, доступных для заявки. Обратитесь к администратору.")
        return
    await state.set_state(IssuanceStates.choosing_warehouse)
    await message.answer("Выберите склад:", reply_markup=kb.warehouses_keyboard(warehouses))


@router.message(F.text == kb.BTN_MENU_EXPENSE)
async def menu_expense(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await _require_employee(message)
    if user is None:
        return
    async with SessionLocal() as session:
        categories = await logic.list_active_expense_categories(session)
    if not categories:
        await message.answer("Нет активных видов расхода. Обратитесь к администратору.")
        return
    await state.set_state(ExpenseStates.choosing_category)
    await message.answer(
        "Выберите вид расхода:", reply_markup=kb.expense_categories_keyboard(categories)
    )


# ══════════════════════ Заявка на товар (спека15 §3) ═══════════════════


@router.callback_query(IssuanceStates.choosing_warehouse, F.data.startswith("wh:"))
async def issuance_pick_warehouse(callback: CallbackQuery, state: FSMContext) -> None:
    warehouse_id = int(callback.data.split(":", 1)[1])
    async with SessionLocal() as session:
        warehouse = await logic.get_warehouse(session, warehouse_id)
    if warehouse is None:
        await callback.answer("Склад не найден, попробуйте снова", show_alert=True)
        return
    await state.update_data(warehouse_id=warehouse.id, warehouse_name=warehouse.name)
    await state.set_state(IssuanceStates.entering_product_query)
    await callback.message.edit_text(f"Склад: {warehouse.name}\nНапишите название товара:")
    await callback.answer()


@router.message(IssuanceStates.entering_product_query, F.text)
async def issuance_search_product(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    if not query:
        await message.answer("Напишите название товара текстом.")
        return
    data = await state.get_data()
    async with SessionLocal() as session:
        result = await resolve_product_query(session, query, data["warehouse_id"])
    await state.set_state(IssuanceStates.choosing_product)
    if not result.matches:
        await message.answer(
            "Ничего не найдено по названию. Попробуйте другое слово или посмотрите весь список:",
            reply_markup=kb.product_matches_keyboard([]),
        )
        return
    hint = "Возможно, вы имели в виду:" if result.source == "ai" else "Похожие товары:"
    await message.answer(hint, reply_markup=kb.product_matches_keyboard(result.matches))


@router.callback_query(IssuanceStates.choosing_product, F.data.startswith("prodlist:"))
async def issuance_show_all_products(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    async with SessionLocal() as session:
        result = await find_all_paginated(
            session, data["warehouse_id"], page, size=_PRODUCT_PAGE_SIZE
        )
    if not result.items:
        await callback.answer("Список товаров пуст", show_alert=True)
        return
    await callback.message.edit_text(
        f"Все товары (стр. {result.page}/{result.pages}):",
        reply_markup=kb.product_page_keyboard(result.items, page=result.page, pages=result.pages),
    )
    await callback.answer()


@router.callback_query(IssuanceStates.choosing_product, F.data.startswith("prod:"))
async def issuance_pick_product(callback: CallbackQuery, state: FSMContext) -> None:
    product_id = int(callback.data.split(":", 1)[1])
    async with SessionLocal() as session:
        product = await logic.get_product(session, product_id)
    if product is None:
        await callback.answer("Товар не найден, попробуйте снова", show_alert=True)
        return
    await state.update_data(product_id=product.id, product_name=product.name)
    await state.set_state(IssuanceStates.entering_qty)
    await callback.message.edit_text(f"Товар: {product.name}\nСколько? (число, больше нуля)")
    await callback.answer()


@router.message(IssuanceStates.entering_qty, F.text)
async def issuance_enter_qty(message: Message, state: FSMContext) -> None:
    qty = logic.parse_positive_decimal(message.text)
    if qty is None:
        await message.answer("Введите число больше нуля, например: 5")
        return
    await state.update_data(qty=str(qty))
    await state.set_state(IssuanceStates.entering_reason)
    await message.answer("Причина получения?")


@router.message(IssuanceStates.entering_reason, F.text)
async def issuance_enter_reason(message: Message, state: FSMContext) -> None:
    reason = message.text.strip()
    if not reason:
        await message.answer("Причина не может быть пустой. Напишите причину получения:")
        return
    await state.update_data(reason=reason)
    data = await state.get_data()
    await state.set_state(IssuanceStates.confirming)
    summary = (
        "Проверьте заявку:\n"
        f"Склад: {data['warehouse_name']}\n"
        f"Товар: {data['product_name']}\n"
        f"Количество: {data['qty']}\n"
        f"Причина: {reason}"
    )
    await message.answer(
        summary, reply_markup=kb.confirm_cancel_keyboard("req_confirm", "req_cancel")
    )


@router.callback_query(IssuanceStates.confirming, F.data == "req_cancel")
async def issuance_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Заявка отменена.")
    await callback.answer()


@router.callback_query(IssuanceStates.confirming, F.data == "req_confirm")
async def issuance_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    async with SessionLocal() as session:
        user = await logic.find_user_by_chat_id(session, callback.message.chat.id)
        if user is None:
            await state.clear()
            await callback.message.edit_text(_SESSION_EXPIRED_TEXT)
            await callback.answer()
            return
        try:
            request = await logic.submit_issuance_request(
                session,
                employee_id=user.id,
                warehouse_id=data["warehouse_id"],
                product_id=data["product_id"],
                qty=Decimal(data["qty"]),
                reason=data["reason"],
            )
        except DomainError as exc:
            # §3 шаг 7: «отказ сервера — текст ошибки сервера как есть,
            # диалог не рвётся» — очищаем состояние, учитель начинает заново
            # через меню, ничего не падает.
            await state.clear()
            await callback.message.edit_text(exc.message)
            await callback.answer()
            return
        except Exception:  # noqa: BLE001 — бот не должен падать на неожиданной ошибке
            logger.exception("Ошибка при создании заявки из бота")
            await state.clear()
            await callback.message.edit_text(
                "Не удалось отправить заявку. Попробуйте ещё раз позже."
            )
            await callback.answer()
            return
    await state.clear()
    await callback.message.edit_text(f"Заявка {request.number} отправлена, ждите выдачи.")
    await callback.answer()


# ══════════════════════ Расход денег (спека15 §4) ══════════════════════


@router.callback_query(ExpenseStates.choosing_category, F.data.startswith("cat:"))
async def expense_pick_category(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = int(callback.data.split(":", 1)[1])
    async with SessionLocal() as session:
        category = await logic.get_expense_category(session, category_id)
    if category is None:
        await callback.answer("Вид расхода не найден, попробуйте снова", show_alert=True)
        return
    await state.update_data(expense_category_id=category.id, expense_category_name=category.name)
    await state.set_state(ExpenseStates.entering_amount)
    await callback.message.edit_text(f"Вид расхода: {category.name}\nСумма в UZS?")
    await callback.answer()


@router.message(ExpenseStates.entering_amount, F.text)
async def expense_enter_amount(message: Message, state: FSMContext) -> None:
    amount = logic.parse_positive_decimal(message.text)
    if amount is None:
        await message.answer("Введите сумму числом больше нуля, например: 50000")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(ExpenseStates.entering_description)
    await message.answer("Опишите расход:")


@router.message(ExpenseStates.entering_description, F.text)
async def expense_enter_description(message: Message, state: FSMContext) -> None:
    description = message.text.strip()
    if not description:
        await message.answer("Описание не может быть пустым. Опишите расход:")
        return
    await state.update_data(description=description)
    await state.set_state(ExpenseStates.waiting_photo)
    await message.answer("Пришлите фото чека.")


@router.message(ExpenseStates.waiting_photo, F.photo)
async def expense_receive_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    photo = message.photo[-1]  # самое крупное разрешение
    file = await bot.get_file(photo.file_id)
    buffer = await bot.download_file(file.file_path)
    receipt_bytes = buffer.read()

    await state.update_data(receipt_bytes=receipt_bytes)
    data = await state.get_data()
    await state.set_state(ExpenseStates.confirming)
    summary = (
        "Проверьте расход:\n"
        f"Вид расхода: {data['expense_category_name']}\n"
        f"Сумма: {data['amount']} UZS\n"
        f"Описание: {data['description']}\n"
        "Чек: приложен"
    )
    await message.answer(
        summary, reply_markup=kb.confirm_cancel_keyboard("exp_confirm", "exp_cancel")
    )


@router.message(ExpenseStates.waiting_photo)
async def expense_reject_non_photo(message: Message) -> None:
    """§4 шаг 4: «Не-фото ввод — переспрашивает»."""
    await message.answer("Пришлите именно фото чека (не текст, не документ, не файл).")


@router.callback_query(ExpenseStates.confirming, F.data == "exp_cancel")
async def expense_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Расход отменён.")
    await callback.answer()


@router.callback_query(ExpenseStates.confirming, F.data == "exp_confirm")
async def expense_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    async with SessionLocal() as session:
        user = await logic.find_user_by_chat_id(session, callback.message.chat.id)
        if user is None:
            await state.clear()
            await callback.message.edit_text(_SESSION_EXPIRED_TEXT)
            await callback.answer()
            return
        try:
            expense = await logic.submit_cash_expense(
                session,
                user=user,
                expense_category_id=data["expense_category_id"],
                amount=Decimal(data["amount"]),
                description=data["description"],
                receipt_bytes=data["receipt_bytes"],
            )
        except DomainError as exc:
            # §4 шаг 6: «Ответ сервера (в т.ч. InsufficientFunds) — прямым
            # текстом» — включая InsufficientFunds, это тоже DomainError.
            await state.clear()
            await callback.message.edit_text(exc.message)
            await callback.answer()
            return
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка при создании расхода из бота")
            await state.clear()
            await callback.message.edit_text(
                "Не удалось отправить расход. Попробуйте ещё раз позже."
            )
            await callback.answer()
            return
    await state.clear()
    await callback.message.edit_text(f"Расход на {expense.amount} UZS отправлен.")
    await callback.answer()


# ══════════════════════ Фолбэк ═══════════════════════════════════════


@router.message(StateFilter(None))
async def fallback(message: Message) -> None:
    """Любое другое сообщение вне диалога — направляем в меню, не молчим."""
    user = await _require_employee(message)
    if user is None:
        return
    await message.answer("Выберите действие в меню:", reply_markup=kb.main_menu_keyboard())
