"""Pydantic v2-схемы модуля auth. DRF-сериализаторы запрещены (ТЗ §0).

Состав каждой схемы определяют API-флаги 02-contract.json → таблица users,
БУКВАЛЬНО:

  атрибут       | get_index | get_single | create | update
  --------------|-----------|------------|--------|-------
  id            |     ✓     |     ✓      |        |
  full_name     |     ✓     |     ✓      |   ✓    |   ✓
  username      |     ✓     |     ✓      |   ✓    |        ← логин не переименовывается
  email         |     ✓     |     ✓      |   ✓    |   ✓    ← М7/ОВ-12; домен проверяет сервис users
  password_hash |           |            |        |        ← наружу не выходит НИКОГДА
  role          |     ✓     |     ✓      |   ✓    |   ✓
  category      |     ✓     |     ✓      |   ✓    |   ✓
  is_active     |     ✓     |     ✓      |        |   ✓    ← ставится только через update
  created_at    |           |     ✓      |        |        ← только в детали
"""

import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enums import UserCategory, UserRole


class UserList(BaseModel):
    """Строка списка. Поля — те, у которых api.get_index = true."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    username: str
    email: str | None
    role: UserRole
    category: UserCategory | None
    is_active: bool


class UserRead(BaseModel):
    """Деталь. Поля — те, у которых api.get_single = true.
    created_at отличает её от UserList: get_index=false, get_single=true."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    username: str
    email: str | None
    role: UserRole
    category: UserCategory | None
    is_active: bool
    created_at: dt.datetime


def _validate_inv9(role: UserRole | None, category: UserCategory | None) -> None:
    """INV-9: users.category IS NULL ⟺ users.role = 'admin'.

    Дублирует CHECK ck_users_category_iff_admin. Смысл дубля — не защита
    (её даёт БД), а внятная русская ошибка вместо 500 от IntegrityError.
    """
    if role is None:
        return
    if role is UserRole.admin and category is not None:
        raise ValueError("Для роли «Администратор» категория не указывается")
    if role is not UserRole.admin and category is None:
        raise ValueError("Для ролей «Учитель» и «Работник» категория обязательна")


class UserCreate(BaseModel):
    """Поля с api.create = true + password.

    password — не колонка: в БД лежит только password_hash (Argon2id), у него
    все четыре API-флага false. Схема принимает сырой пароль на вход и никогда
    его не возвращает; хеширование — в сервисе, до записи.
    """

    # Словарь данных описывает колонки БД, а password колонкой не является —
    # это поле ввода API. Маркер разрешает его валидатору контракта явно,
    # чтобы гейт не пришлось ослаблять ради одного легального исключения.
    __contract_extra_fields__ = {"password"}

    full_name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=150)
    # М7/ОВ-12: формат и домен (@npuu.uz, settings.email_domain) проверяет
    # СЕРВИС users, не схема: домен — конфигурация, а схема настроек не знает.
    email: str | None = Field(default=None, max_length=255)
    role: UserRole
    category: UserCategory | None = None
    password: str = Field(min_length=8, max_length=128, repr=False)

    @model_validator(mode="after")
    def _check_inv9(self) -> Self:
        _validate_inv9(self.role, self.category)
        return self


class UserUpdate(BaseModel):
    """Поля с api.update = true. Все опциональны — семантика PATCH.

    username отсутствует намеренно: контракт даёт ему create=true, update=false.
    password_hash отсутствует: все флаги false.

    INV-9 здесь НЕ проверяется: PATCH частичен, и role без category (или
    наоборот) в теле легален — инвариант проверяет сервис users по
    ИТОГОВОМУ состоянию (текущее + патч), где обе половины известны.
    """

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    role: UserRole | None = None
    category: UserCategory | None = None
    is_active: bool | None = None


# ── Аутентификация ──────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=128, repr=False)


class TokenResponse(BaseModel):
    """Refresh-токена в теле НЕТ: он уходит только httpOnly+Secure cookie (§9).
    Отдать его здесь означало бы вернуть JS-коду ровно то, что cookie и прячет."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
