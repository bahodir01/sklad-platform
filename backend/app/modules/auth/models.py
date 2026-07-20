"""М1/М7: users. Модель перенесена из 02-database.md §6 без переписывания.

Контракт (02-contract.json → users): id, full_name, username, password_hash,
role, category, is_active, created_at, email.

email добавлен модулем М7 «Пользователи» (ОВ-12, реализована только часть
CRUD+email; публичные формы отложены). Уникальность — частичным индексом
WHERE email IS NOT NULL: обычный UNIQUE в PostgreSQL несколько NULL и так
пропускает, но частичный индекс фиксирует это намерение явно и не
индексирует толпу строк с email=NULL (сид-пользователи и все заведённые
без почты).
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
        Index("ix_users_role", "role"),
        # М7: UNIQUE среди непустых email; несколько NULL не конфликтуют.
        Index(
            "uq_users_email_not_null",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    # М7/ОВ-12: корпоративная почта @npuu.uz (домен — settings.email_domain).
    # Формат и домен валидирует сервис users; хранится в нижнем регистре.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
