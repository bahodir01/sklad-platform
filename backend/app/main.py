"""Сборка FastAPI: middleware, exception handlers, роутеры. Архитектура §3.

Стек: FastAPI + SQLAlchemy 2.0 + Pydantic v2 + PostgreSQL 16.
Django/DRF в проекте отсутствуют (ТЗ §0 — согласовано подписью заказчика).

ЭТАП 1 «Фундамент» (ТЗ §11): core/*, modules/auth, modules/catalog, Alembic,
docker-compose. Роутеры М2–М6 подключаются на своих этапах; их модели уже
созданы (схема заморожена и накатывается одной начальной миграцией).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# Импорт реестра моделей обязателен: без него SQLAlchemy не разрешит
# строковые ссылки в relationship() между модулями.
import app.models  # noqa: F401
from app.core.audit import AuditMiddleware
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.tokens import close_redis, get_redis
from app.modules.cash.router import router as cash_router
from app.modules.catalog.router import router as catalog_router
from app.modules.documents.router import router as documents_router
from app.modules.issuance.router import router as issuance_router
from app.modules.reports.router import router as reports_router
from app.modules.stock.router import router as stock_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_redis()
    yield
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Платформа складского учёта, документооборота и учёта денежных средств. "
        "Этап 1 «Фундамент»: аутентификация, RBAC, справочники (М1)."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Порядок middleware важен: CORS должен быть внешним, иначе браузер не увидит
# заголовков на ответах, сформированных внутренними слоями.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,  # refresh-cookie
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
app.add_middleware(AuditMiddleware)

register_exception_handlers(app)

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(catalog_router, prefix=settings.api_prefix)
# ЭТАП 2 «Товародвижение» (ТЗ §11): документооборот М2 + ядро учёта М3.
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(stock_router, prefix=settings.api_prefix)
# ЭТАП 3 «Заявки и печать» (ТЗ §11): статусная машина заявки, очередь печати,
# issue() + проводка (modules/issuance).
app.include_router(issuance_router, prefix=settings.api_prefix)
# ЭТАП 4 «Расходы товара» (ТЗ §11): порча/брак — прямое создание writeoff без
# заявки (POST /writeoffs в modules/issuance, таблица и ledger готовы с этапа 3).
# ЭТАП 5 «Деньги» (ТЗ §11): кассы, приход, расход, чеки (modules/cash).
app.include_router(cash_router, prefix=settings.api_prefix)
# ЭТАП 6 «Отчётность» (ТЗ §11): остатки, недокуп, история, ДДС + экспорт
# xlsx/pdf (modules/reports). Read-only поверх готовых таблиц, новых моделей нет.
app.include_router(reports_router, prefix=settings.api_prefix)
# М7 «Администрирование»: алерты админ-панели (Q3 заказчика — уведомления внутри
# панели). Read-only, схему не трогает: алерты выводятся из состояния на лету.
app.include_router(admin_router, prefix=settings.api_prefix)


@app.get("/health", tags=["ops"], summary="Liveness-проба")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["ops"], summary="Readiness-проба")
async def ready() -> dict[str, str]:
    """Архитектура §9: /health + /ready для оркестратора.

    Проверяет зависимости по-настоящему: контейнер, поднявшийся без БД или
    Redis, обязан не получать трафик. Недоступная зависимость — это 503
    (Service Unavailable), а не 500: оркестратор ждёт именно 503, а 500
    засорял бы алерты необработанным исключением на каждой пробе.
    """
    from sqlalchemy import text

    from app.core.database import engine

    failures: list[str] = []
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — проба обязана поймать любую ошибку связи
        failures.append(f"db: {exc.__class__.__name__}")
    try:
        await get_redis().ping()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"redis: {exc.__class__.__name__}")

    if failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "failed": failures},
        )
    return {"status": "ready"}
