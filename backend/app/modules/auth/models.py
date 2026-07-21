"""М1/М7: users. Модель перенесена из 02-database.md §6 без переписывания.

Контракт (02-contract.json → users): id, full_name, username, password_hash,
role, category, is_active, created_at, email, phone, telegram_chat_id.

email добавлен модулем М7 «Пользователи» (ОВ-12, реализована только часть
CRUD+email; публичные формы отложены). Уникальность — частичным индексом
WHERE email IS NOT NULL: обычный UNIQUE в PostgreSQL несколько NULL и так
пропускает, но частичный индекс фиксирует это намерение явно и не
индексирует толпу строк с email=NULL (сид-пользователи и все заведённые
без почты).

phone и telegram_chat_id добавлены миграцией 0004 (спека15 §2, Telegram-бот):
привязка Telegram-аккаунта к пользователю по номеру телефона. Оба поля
nullable + частичный UNIQUE (WHERE ... IS NOT NULL), по тому же паттерну,
что email. phone заполняет админ через модуль «Пользователи» (create/update);
telegram_chat_id пишет ТОЛЬКО бот в момент успешной привязки — сервисное
поле, обычному API создания/правки пользователя недоступно.
"""

import datetime as dt

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import UserCategory, UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(trim(full_name)) > 0", name="ck_users_full_name_not_blank"),
        # INV-9: category IS NULL ⟺ role = 'admin'.
        # Дублируется валидатором в UserCreate/UserUpdate (Pydantic), но
        # источник истины — этот CHECK: приложение его не обходит.
        CheckConstraint(
            "(category IS NULL) = (role = 'admin')",
            name="ck_users_category_iff_admin",
        ),
        # спека15 §2: базовая защита формата в БД (только цифры с ведущим '+',
        # 9..15 цифр — примерный диапазон E.164). Полную нормализацию
        # (пробелы/скобки/локальные форматы ввода админом) делает сервис
        # users при сохранении — БД лишь отбивает явный мусор.
        CheckConstraint(
            r"phone IS NULL OR phone ~ '^\+\d{9,15}$'",
            name="ck_users_phone_format",
        ),
        Index("ix_users_role", "role"),
        # М7: UNIQUE среди непустых email; несколько NULL не конфликтуют.
        Index(
            "uq_users_email_not_null",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        # спека15 §2: один Telegram-аккаунт — один пользователь, и наоборот
        # (уникальность в обе стороны — обе колонки partial-unique).
        Index(
            "uq_users_phone_not_null",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
        Index(
            "uq_users_telegram_chat_id_not_null",
            "telegram_chat_id",
            unique=True,
            postgresql_where=text("telegram_chat_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    # М7/ОВ-12: корпоративная почта @npuu.uz (домен — settings.email_domain).
    # Формат и домен валидирует сервис users; хранится в нижнем регистре.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # спека15 §2: телефон для привязки Telegram-аккаунта. Нормализованный
    # формат (напр. +998901234567) — нормализацию делает сервис users при
    # сохранении; ck_users_phone_format — только защита от мусора в БД.
    # Заполняет админ через create/update; бот в это поле не пишет.
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # ТЗ §7: Argon2id. Наружу не отдаётся ни в одной Pydantic-схеме
    # (api: get_index/get_single/create/update — все false) и не логируется.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), nullable=False
    )
    category: Mapped[UserCategory | None] = mapped_column(
        SAEnum(UserCategory, name="user_category"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # спека15 §2: заполняется ТОЛЬКО ботом в момент успешной привязки по
    # телефону — не обычным API создания/правки пользователя (api.create =
    # api.update = false в контракте). Сервисное поле.
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
