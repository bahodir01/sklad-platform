"""М1/М7: users. Модель перенесена из 02-database.md §6 без переписывания.

Контракт (02-contract.json → users): id, full_name, username, password_hash,
role, category, is_active, created_at.
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
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
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
