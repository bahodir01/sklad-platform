"""Клавиатуры бота (спека15 §2-§4): reply-меню + inline-выбор/подтверждение.

Строится из простых объектов с ``.id``/``.name`` (ORM-модели каталога и
``ProductMatch`` из ``modules/ai/schemas.py`` одинаково подходят) — модуль не
завязан на конкретный тип, чтобы не тащить сюда импорты моделей БД.
"""

from typing import Protocol

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

BTN_REQUEST_PHONE = "📱 Отправить номер телефона"
BTN_MENU_ISSUANCE = "📦 Заявка на товар"
BTN_MENU_EXPENSE = "💵 Расход денег"
BTN_SHOW_ALL = "📋 Показать весь список"
BTN_CONFIRM = "✅ Отправить"
BTN_CANCEL = "❌ Отмена"

CB_SHOW_ALL_PRODUCTS = "prodlist:1"


class _NamedRow(Protocol):
    id: int
    name: str


def request_phone_keyboard() -> ReplyKeyboardMarkup:
    """§2 шаг 2: единственная reply-кнопка ``request_contact``."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_REQUEST_PHONE, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню после привязки: «Заявка на товар» / «Расход денег»."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_MENU_ISSUANCE), KeyboardButton(text=BTN_MENU_EXPENSE)]],
        resize_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def warehouses_keyboard(warehouses: list[_NamedRow]) -> InlineKeyboardMarkup:
    """§3 шаг 1: только склады ``allows_issuance=true`` (список уже
    отфильтрован вызывающим кодом — ``logic.list_issuance_warehouses``)."""
    rows = [[InlineKeyboardButton(text=w.name, callback_data=f"wh:{w.id}")] for w in warehouses]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_matches_keyboard(matches: list[_NamedRow]) -> InlineKeyboardMarkup:
    """§3 шаг 3: до 5 кандидатов кнопками + «Показать весь список» (всегда
    доступна, даже если ``matches`` пуст — ручная альтернатива)."""
    rows = [[InlineKeyboardButton(text=m.name, callback_data=f"prod:{m.id}")] for m in matches]
    rows.append([InlineKeyboardButton(text=BTN_SHOW_ALL, callback_data=CB_SHOW_ALL_PRODUCTS)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_page_keyboard(items: list[_NamedRow], *, page: int, pages: int) -> InlineKeyboardMarkup:
    """§3 шаг 3.3: постраничный список всей номенклатуры + Вперёд/Назад."""
    rows = [[InlineKeyboardButton(text=p.name, callback_data=f"prod:{p.id}")] for p in items]
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="« Назад", callback_data=f"prodlist:{page - 1}"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="Вперёд »", callback_data=f"prodlist:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def expense_categories_keyboard(categories: list[_NamedRow]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=c.name, callback_data=f"cat:{c.id}")] for c in categories]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_cancel_keyboard(confirm_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    """§3 шаг 6 / §4 шаг 5: «✅ Отправить» / «❌ Отмена» под резюме."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=BTN_CONFIRM, callback_data=confirm_cb),
                InlineKeyboardButton(text=BTN_CANCEL, callback_data=cancel_cb),
            ]
        ]
    )
