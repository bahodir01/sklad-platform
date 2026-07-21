"""Telegram-бот + экран «Интеграции» (спека15 §2, §5а)

Схема ЗАМОРОЖЕНА и накатана поверх 0003 (живая БД). Эта ревизия только
ДОБАВЛЯЕТ — 0001/0002/0003 не трогает.

1. users.phone (спека15 §2) — varchar(20), nullable, частичный UNIQUE
   WHERE phone IS NOT NULL. Формат хранения нормализованный (E.164-подобный,
   напр. +998901234567); нормализацию делает сервис users при сохранении,
   БД добавляет только CHECK-заслон от явного мусора
   (^\\+\\d{9,15}$, PostgreSQL ARE — \\d поддерживается).

2. users.telegram_chat_id (спека15 §2) — bigint, nullable, частичный UNIQUE
   WHERE telegram_chat_id IS NOT NULL. Пишет ТОЛЬКО бот при успешной
   привязке — сервисное поле, обычному API создания/правки пользователя
   недоступно (api.create = api.update = false в контракте).

   Один Telegram-аккаунт — один пользователь и наоборот: уникальность
   в обе стороны (обе колонки partial-unique), как требует спека15 §2.

3. integration_settings (спека15 §5а) — единое место внешних ключей
   (Telegram-бот, ИИ-поиск), ровно одна строка на kind. kind — обычный
   varchar(32), не enum: набор типов интеграций может расшириться INSERT-ом
   новой строки без ALTER TYPE. secret_encrypted хранит уже готовый
   шифротекст — БД шифрованием не занимается, ключ у сервиса из .env.
   Сеются ровно две строки: 'telegram' и 'ai_search', is_enabled=false,
   secret_encrypted=NULL, updated_by=NULL — до первой настройки админом
   через экран «Интеграции» (по аналогии с seed двух cash_desks в 0001).

Revision ID: 0004_telegram_bot
Revises: 0003_users_email
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_telegram_bot"
down_revision: str | None = "0003_users_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PHONE_FORMAT_CHECK = r"phone IS NULL OR phone ~ '^\+\d{9,15}$'"


def upgrade() -> None:
    # ── users.phone (спека15 §2) ──────────────────────────────────────
    op.add_column("users", sa.Column("phone", sa.String(20), nullable=True))
    op.create_check_constraint("ck_users_phone_format", "users", PHONE_FORMAT_CHECK)
    op.create_index(
        "uq_users_phone_not_null",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )

    # ── users.telegram_chat_id (спека15 §2) ───────────────────────────
    op.add_column("users", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.create_index(
        "uq_users_telegram_chat_id_not_null",
        "users",
        ["telegram_chat_id"],
        unique=True,
        postgresql_where=sa.text("telegram_chat_id IS NOT NULL"),
    )

    # ── integration_settings (спека15 §5а) ────────────────────────────
    op.create_table(
        "integration_settings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(32), nullable=False, unique=True),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column(
            "is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_integration_settings_updated_by", "integration_settings", ["updated_by"]
    )

    # Ровно две строки — telegram и ai_search. Новых kind через API не
    # создают; добавление нового типа интеграции — отдельная миграция
    # с INSERT, как эта (UNIQUE(kind) не даёт завести вторую строку одного
    # типа даже по ошибке).
    op.execute(
        "INSERT INTO integration_settings (kind, is_enabled) "
        "VALUES ('telegram', false), ('ai_search', false)"
    )


def downgrade() -> None:
    op.drop_table("integration_settings")

    op.drop_index("uq_users_telegram_chat_id_not_null", table_name="users")
    op.drop_column("users", "telegram_chat_id")

    op.drop_index("uq_users_phone_not_null", table_name="users")
    op.drop_constraint("ck_users_phone_format", "users", type_="check")
    op.drop_column("users", "phone")
