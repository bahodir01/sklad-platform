"""Engine, sessionmaker, get_session, DeclarativeBase.

Архитектура §3: core/database.py. §2 «Правило слоёв»: транзакция открывается
на уровне сервиса — один HTTP-запрос = одна транзакция. get_session отдаёт
сессию без автокоммита: коммитит сервис, когда бизнес-инвариант целостен.

Стек — SQLAlchemy 2.0 (DeclarativeBase / Mapped / mapped_column). Django ORM
запрещён (ТЗ §0).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Базовый класс всех 22 моделей схемы."""


engine = create_async_engine(
    settings.database_url_str,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=settings.db_pool_pre_ping,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: сессия на время запроса.

    Коммит — обязанность сервисного слоя (архитектура §2). Здесь только
    гарантированный rollback при исключении и закрытие соединения.
    """
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
