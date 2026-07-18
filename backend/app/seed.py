"""Начальные данные, не входящие в схему.

    python -m app.seed

ДВЕ КАССЫ ЗДЕСЬ НЕ СОЗДАЮТСЯ. Они — часть начальной миграции
(0001_initial_schema.py), потому что их существование это инвариант схемы,
а не опциональные демо-данные: money_expense.cash_desk_id NOT NULL, и без
двух строк cash_desks система нерабочая. Через API они не создаются тоже.

Здесь — только стартовый администратор: без него в системе невозможно
завести ни одного пользователя, а регистрации в ТЗ нет (пользователей
заводит завскладом). Идемпотентен: повторный запуск ничего не ломает.
"""

import asyncio
import os
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.cash.models import CashDesk
from app.shared.enums import UserRole


async def seed_admin(username: str, password: str, full_name: str) -> None:
    async with SessionLocal() as session:
        existing = await session.scalar(select(User).where(User.username == username))
        if existing is not None:
            print(f"Администратор «{username}» уже существует — пропуск")
            return

        session.add(
            User(
                full_name=full_name,
                username=username,
                password_hash=hash_password(password),  # Argon2id
                role=UserRole.admin,
                category=None,  # INV-9: у admin категории нет
                is_active=True,
            )
        )
        await session.commit()
        print(f"Создан администратор «{username}»")


async def verify_cash_desks() -> None:
    """Проверка, а не создание: кассы ставит миграция."""
    async with SessionLocal() as session:
        rows = list(await session.scalars(select(CashDesk)))
        types = sorted(desk.type.value for desk in rows)
        if types != ["teacher", "worker"]:
            raise SystemExit(
                f"Кассы в БД: {types or 'нет'}. Ожидались ровно две (teacher, worker). "
                f"Накатите миграции: alembic upgrade head"
            )
        print("Кассы на месте: teacher, worker")


async def main() -> None:
    password = os.environ.get("SEED_ADMIN_PASSWORD")
    if not password:
        print(
            "SEED_ADMIN_PASSWORD не задан. Пароль администратора не генерируется "
            "автоматически: сгенерированный пароль пришлось бы напечатать в лог, "
            "а логи попадают в общий сборщик.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    await verify_cash_desks()
    await seed_admin(
        username=os.environ.get("SEED_ADMIN_USERNAME", "admin"),
        password=password,
        full_name=os.environ.get("SEED_ADMIN_FULL_NAME", "Заведующий складом"),
    )


if __name__ == "__main__":
    asyncio.run(main())
