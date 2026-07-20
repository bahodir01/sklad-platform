"""Схемы модуля users (М7 «Пользователи», ОВ-12 — часть CRUD+email).

Контрактные схемы пользователя (UserList/UserRead/UserCreate/UserUpdate)
живут в modules/auth/schemas.py и НЕ дублируются здесь: у валидатора
контракта класс идентифицируется по имени, и вторая UserCreate в другом
файле молча перекрыла бы первую при проверке. Модуль реиспользует их.

Здесь — только то, что колонкой users не является.
"""

from pydantic import BaseModel, Field

from app.modules.auth.schemas import (  # noqa: F401 — реэкспорт для роутера/сервиса
    UserCreate,
    UserList,
    UserRead,
    UserUpdate,
)


class PasswordResetIn(BaseModel):
    """Тело POST /users/{id}/reset-password.

    Имя без суффиксов Create/Update/Read/List — контрактный валидатор такие
    классы пропускает: password не колонка, таблицы за схемой нет.
    Ограничения — те же, что у password в UserCreate (мин. 8).
    """

    password: str = Field(min_length=8, max_length=128, repr=False)
