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

    # ── JWT (ТЗ §7 «Безопасность», архитектура §9) ───────────────────
    # access — 15 минут, живёт в памяти JS (не в localStorage: XSS-кража)
    # refresh — 30 дней, только httpOnly + Secure + SameSite cookie
    jwt_secret: str = Field(default="CHANGE-ME-IN-PRODUCTION", min_length=8)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    jwt_issuer: str = "sklad-api"

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
