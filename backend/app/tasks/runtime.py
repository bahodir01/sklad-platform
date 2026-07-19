"""Мост «синхронный Celery ↔ асинхронный сервисный слой».

Всё приложение асинхронное (asyncpg, AsyncSession, ledger, reports). Celery-
задачи по умолчанию синхронны, поэтому каждая задача запускает свою корутину
через ``asyncio.run``.

ПОЧЕМУ СВОЙ ENGINE НА ЗАДАЧУ, А НЕ ОБЩИЙ app.core.database.engine.
Модульный ``engine`` создаётся при импорте и держит пул asyncpg-соединений,
привязанных к event loop, в котором они открыты. ``asyncio.run`` каждый вызов
создаёт НОВЫЙ loop; переиспользование того же пула в другом loop роняет asyncpg
с «attached to a different loop». Поэтому задача поднимает NullPool-engine на
время своего выполнения и гарантированно закрывает его в finally — соединения
не переживают задачу и не утекают между loop-ами.

Задачи запускаются нечасто (beat-регламент, точечный прогрев PDF), поэтому цена
создания engine на вызов пренебрежимо мала по сравнению с надёжностью.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

_T = TypeVar("_T")


def run_async(coro: Awaitable[_T]) -> _T:
    """Выполнить корутину в свежем event loop. Точка входа синхронной задачи."""
    return asyncio.run(coro)  # type: ignore[arg-type]


@asynccontextmanager
async def task_session() -> AsyncIterator[AsyncSession]:
    """Изолированная сессия задачи на NullPool-engine (см. модульный docstring).

    Коммит — обязанность вызывающего кода (как и в app.core.database.get_session):
    здесь только гарантированный rollback при исключении, закрытие сессии и
    dispose engine, чтобы соединение не пережило текущий loop.
    """
    engine = create_async_engine(settings.database_url_str, poolclass=NullPool)
    maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    try:
        async with maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()


async def with_session(fn: Callable[[AsyncSession], Awaitable[_T]]) -> _T:
    """Сахар: открыть task_session и передать её в корутину-обработчик."""
    async with task_session() as session:
        return await fn(session)
