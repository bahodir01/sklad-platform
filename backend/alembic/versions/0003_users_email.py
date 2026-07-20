"""users.email — модуль М7 «Пользователи» (ОВ-12, часть CRUD+email)

Заказчик (ОВ-12, 19.07.2026): админ/завсклад заводит сотрудников через
админ-панель; у пользователя появляется корпоративная почта @npuu.uz для
будущих публичных форм. Здесь — только колонка; публичные формы отложены.

Колонка nullable: существующие сид-пользователи остаются с email=NULL —
это валидное состояние (почта опциональна и сейчас, и по ОВ-12 обязательна
станет только для тех, кто пользуется публичными формами).

Уникальность — ЧАСТИЧНЫМ unique-индексом WHERE email IS NOT NULL, а не
UNIQUE-constraint'ом: намерение «много NULL допустимо, непустые не
повторяются» выражено явно, и индекс не хранит записи для толпы
пользователей без почты.

Revision ID: 0003_users_email
Revises: 0002_batch_signature
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_users_email"
down_revision: str | None = "0002_batch_signature"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(255), nullable=True))
    op.create_index(
        "uq_users_email_not_null",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_not_null", table_name="users")
    op.drop_column("users", "email")
