"""Конфигурация приложения (pydantic-settings). Архитектура §3: core/config.py."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Общее ───────────────────────────────────────────────────────
    app_name: str = "Платформа складского учёта"
    environment: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # ── PostgreSQL 16 ───────────────────────────────────────────────
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://sklad:sklad@db:5432/sklad",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    # ── Redis (брокер/кеш + хранилище refresh-сессий) ────────────────
    redis_url: RedisDsn = Field(default="redis://redis:6379/0")

    # ── Celery (фоновые задачи, архитектура §8) ──────────────────────
    # Отдельные логические БД Redis: /1 — брокер, /2 — result backend, чтобы
    # очереди задач и их результаты не смешивались с кешом приложения (/0).
    # ВНИМАНИЕ про RESP2/RESP3: redis-py 8 по умолчанию RESP3 и шлёт HELLO,
    # которого Redis 5 не знает → соединение падает.
    #   * result backend (redis-py from_url) — понимает ?protocol=2 в URL;
    #   * брокер (kombu redis transport) — параметр ?protocol=2 НЕ принимает и
    #     падает на нём. Для него RESP2 включается глобально в процессе Celery
    #     (redis.connection.DEFAULT_RESP_VERSION=2, см. tasks/celery_app.py),
    #     поэтому в broker URL параметр НЕ ставим.
    celery_broker_url: str = Field(default="redis://redis:6379/1")
    celery_result_backend: str = Field(default="redis://redis:6379/2?protocol=2")
    # Расписание beat считается в этой зоне: 03:00 ревизии — местная ночь (UZS).
    celery_timezone: str = "Asia/Tashkent"

    # ── Фоновый экспорт отчётов (задача export_report, архитектура §8) ─
    # Порог «маленький ↔ большой» отчёт: до порога роутер отдаёт файл синхронно
    # (обратная совместимость с ?format=), выше — через Celery-задачу.
    export_sync_row_cap: int = 5_000
    # Жёсткий потолок строк выгрузки (и синхронной, и фоновой), чтобы не тянуть
    # миллионы строк истории в память одного воркера.
    export_row_cap: int = 100_000
    s3_bucket_exports_prefix: str = "exports"

    # ── Бэкап БД (задача db_backup, ТЗ §9 «Отказоустойчивость») ───────
    # Путь к pg_dump. В prod — на PATH контейнера (образ postgres-client).
    # Если бинарь недоступен, задача делает COPY-based логический фолбэк
    # (тот же приём graceful-fallback, что WeasyPrint→HTML и MinIO→локально).
    pg_dump_path: str = "pg_dump"
    s3_bucket_backups_prefix: str = "backups"

    # ── Черновик пополнения касс (задача monthly_income_draft, §7.2) ──
    # ВАЖНО: money_income НЕ имеет статуса draft (схема заморожена). Задача НЕ
    # проводит приход и НЕ пишет в БД — она формирует УВЕДОМЛЕНИЕ администратору
    # (артефакт-черновик в объектном хранилище + структурный алерт). Префикс —
    # ключ артефакта, один на месяц (идемпотентность).
    s3_bucket_income_drafts_prefix: str = "drafts/income"

    # ── JWT (ТЗ §7 «Безопасность», архитектура §9) ───────────────────
    # access — 15 минут, живёт в памяти JS (не в localStorage: XSS-кража)
    # refresh — 30 дней, только httpOnly + Secure + SameSite cookie
    jwt_secret: str = Field(default="CHANGE-ME-IN-PRODUCTION", min_length=8)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    jwt_issuer: str = "sklad-api"

    # ── Шифрование секретов интеграций (спека15 §5а) ─────────────────
    # Telegram-токен и ключ ИИ-поиска хранятся в integration_settings
    # зашифрованными (Fernet-ключ, производный от этой строки — см.
    # shared/crypto.py), тем же принципом, что jwt_secret выше: секрет живёт
    # в .env, не в схеме БД и не хардкодом. ОБЯЗАТЕЛЬНО заменить в prod.
    integration_secret_key: str = Field(
        default="CHANGE-ME-IN-PRODUCTION-INTEGRATION-KEY-32B", min_length=32
    )

    # ── Refresh-cookie ──────────────────────────────────────────────
    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_path: str = "/api/v1/auth"
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # В dev по HTTP Secure-cookie браузер не отдаст; в prod — всегда True.
    refresh_cookie_secure: bool = True
    refresh_cookie_domain: str | None = None

    # ── Argon2id (ТЗ §7: пароли только Argon2id) ─────────────────────
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536  # 64 MiB
    argon2_parallelism: int = 4
    argon2_hash_len: int = 32
    argon2_salt_len: int = 16

    # ── MinIO / S3 (используется с этапа 3+; конфиг заводится сейчас) ─
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_receipts: str = "receipts"
    s3_bucket_documents: str = "documents"
    s3_presigned_ttl_seconds: int = 300  # 5 минут (ТЗ §7)
    s3_max_upload_bytes: int = 10 * 1024 * 1024  # 10 МБ

    # ── М7 «Пользователи» (ОВ-12, часть CRUD+email) ──────────────────
    # Разрешённый домен корпоративной почты. Валидация в modules/users:
    # email, если задан, обязан быть <local>@<email_domain>. Конфигурируем
    # намеренно: у заказчика домен npuu.uz, но это настройка, не константа кода.
    email_domain: str = "npuu.uz"

    # ── Пагинация ───────────────────────────────────────────────────
    page_size_default: int = 50
    page_size_max: int = 200

    # ── Реквизиты организации для бланка BILDIRISHNOMA (ТЗ §3 М2) ─────
    # Печатается на PDF-уведомлении. В БД эти строки не хранятся (решение
    # заказчика: ректор/проректор/подпись — константы приложения). Шапка —
    # ЦЕЛЫМИ строками, а не «ФИО + окончание»: узбекский аффикс зависит от
    # последней буквы основы, склейка в шаблоне однажды напечатала бы неверную
    # форму в официальном документе (ТЗ §3 М2, комментарий в шаблоне).
    org_addressee_line1: str = "Andijon davlat universiteti"
    org_addressee_line2: str = "rektori A.A.Yo‘ldoshevga"
    org_sender_line1: str = "Xo‘jalik bo‘limi mudiri"
    org_sender_line2: str = "B.B.Umarovadan"
    org_signer_position: str = "Xo‘jalik bo‘limi mudiri"
    org_signer_name: str = "B.B.Umarova"

    # Каталог Jinja2-шаблонов печатных форм (архитектура §3).
    templates_dir: str = "app/templates/pdf"

    # ── CORS ────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)

    @property
    def redis_url_str(self) -> str:
        return str(self.redis_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
