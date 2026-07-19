"""batch signature & submission tracking (фича 13)

Спека: .feature-dev/13-batch-signature-spec.md (§2 статусы, §3 signature_batches,
§4 поля передачи, §6 ограничения).

0001 УЖЕ накатана на живую БД и НЕ правится. Это ревизия поверх неё:

  §2  requests.status: draft|to_print|printed|issued → draft|to_issue|issued|
      signed|submitted. Data migration: to_print→to_issue, printed→to_issue.
      Списание переехало на to_issue → issued; INV-2 расширен до issued/signed/
      submitted.
  §3  Новая таблица signature_batches + requests.batch_id (FK, RESTRICT, индекс).
  §4  Колонки передачи: requests.submitted_at/submitted_register_no,
      money_expense.submitted_at/submitted_register_no. Частичный индекс
      «не передано» для денег (у денег нет статуса — только submitted_at).

── Как решён ALTER enum ──────────────────────────────────────────────────────
PostgreSQL не умеет удалять значения из enum, а `ALTER TYPE ... ADD VALUE`
нельзя использовать в той же транзакции, где значение затем читается. Нужно и
добавить (to_issue/signed/submitted), и убрать (to_print/printed) — поэтому тип
ПЕРЕСОЗДаётся, а не патчится:

    rename старый тип → create новый → ALTER COLUMN ... TYPE ... USING(CASE ...)
    → drop старый тип.

Всё это транзакционно-безопасно (в отличие от ADD VALUE) и заодно ремапит
данные. Перед сменой типа снимаются зависящие от старых значений объекты:
частичный индекс ix_requests_to_print (предикат WHERE status='to_print') и
CHECK INV-2 (переписывается на новый набор статусов); default 'draft'
снимается и возвращается вокруг смены типа.

Совместимость INV-2 со старыми данными: прежние issued уже имеют writeoff_id
(гарантия старого INV-2), новый CHECK для них истинен; to_print/printed →
to_issue имеют writeoff_id IS NULL и тоже проходят.

Revision ID: 0002_batch_signature
Revises: 0001_initial
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_batch_signature"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── §3. signature_batches ───────────────────────────────────────────
    op.create_table(
        "signature_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("number", sa.String(32), nullable=False, unique=True),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "period_from <= period_to", name="ck_signature_batches_period_order"
        ),
    )
    op.create_index("ix_signature_batches_created_by", "signature_batches", ["created_by"])

    # ── §2. request_status: пересоздание типа + data migration ──────────
    # Снять всё, что ссылается на старые значения, ДО смены типа.
    op.execute("DROP INDEX IF EXISTS ix_requests_to_print")
    op.execute(
        "ALTER TABLE requests DROP CONSTRAINT IF EXISTS ck_requests_issued_iff_posted"
    )
    op.execute("ALTER TABLE requests ALTER COLUMN status DROP DEFAULT")

    op.execute("ALTER TYPE request_status RENAME TO request_status_old")
    op.execute(
        "CREATE TYPE request_status AS ENUM "
        "('draft', 'to_issue', 'issued', 'signed', 'submitted')"
    )
    # Data migration (спека §2): to_print/printed → to_issue; остальное 1:1.
    op.execute(
        "ALTER TABLE requests ALTER COLUMN status TYPE request_status USING ("
        "CASE status::text "
        "WHEN 'to_print' THEN 'to_issue' "
        "WHEN 'printed' THEN 'to_issue' "
        "ELSE status::text END"
        ")::request_status"
    )
    op.execute("ALTER TABLE requests ALTER COLUMN status SET DEFAULT 'draft'")
    op.execute("DROP TYPE request_status_old")

    # INV-2 обновлён: проводка есть на issued/signed/submitted.
    op.create_check_constraint(
        "ck_requests_issued_iff_posted",
        "requests",
        "(status IN ('issued','signed','submitted')) = (writeoff_id IS NOT NULL)",
    )

    # ── §3/§4. requests: batch_id + поля передачи ───────────────────────
    op.add_column("requests", sa.Column("batch_id", sa.BigInteger(), nullable=True))
    op.add_column("requests", sa.Column("submitted_at", sa.Date(), nullable=True))
    op.add_column(
        "requests", sa.Column("submitted_register_no", sa.String(32), nullable=True)
    )
    op.create_foreign_key(
        "fk_requests_batch_id",
        "requests",
        "signature_batches",
        ["batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_requests_batch_id", "requests", ["batch_id"])

    # ── §4. money_expense: поля передачи + частичный индекс «не передано» ─
    op.add_column("money_expense", sa.Column("submitted_at", sa.Date(), nullable=True))
    op.add_column(
        "money_expense", sa.Column("submitted_register_no", sa.String(32), nullable=True)
    )
    op.execute(
        "CREATE INDEX ix_money_expense_not_submitted ON money_expense (id) "
        "WHERE submitted_at IS NULL"
    )


def downgrade() -> None:
    # ── §4. money_expense ───────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS ix_money_expense_not_submitted")
    op.drop_column("money_expense", "submitted_register_no")
    op.drop_column("money_expense", "submitted_at")

    # ── §3/§4. requests: batch_id + поля передачи ───────────────────────
    op.drop_index("ix_requests_batch_id", table_name="requests")
    op.drop_constraint("fk_requests_batch_id", "requests", type_="foreignkey")
    op.drop_column("requests", "submitted_register_no")
    op.drop_column("requests", "submitted_at")
    op.drop_column("requests", "batch_id")

    # ── §2. request_status: возврат к draft/to_print/printed/issued ──────
    # ОГРАНИЧЕНИЕ downgrade (задокументировано в 13a-schema-batch.md):
    # обратный ремап НЕОБРАТИМ семантически — to_issue→to_print (произвольно, но
    # ближе всего к «до печати»), а signed/submitted схлопываются в issued, т.к.
    # старой модели этих состояний не существовало. Структура восстанавливается
    # полностью, часть исторической информации о подписи/передаче теряется.
    op.execute(
        "ALTER TABLE requests DROP CONSTRAINT IF EXISTS ck_requests_issued_iff_posted"
    )
    op.execute("ALTER TABLE requests ALTER COLUMN status DROP DEFAULT")

    op.execute("ALTER TYPE request_status RENAME TO request_status_new")
    op.execute(
        "CREATE TYPE request_status AS ENUM "
        "('draft', 'to_print', 'printed', 'issued')"
    )
    op.execute(
        "ALTER TABLE requests ALTER COLUMN status TYPE request_status USING ("
        "CASE status::text "
        "WHEN 'to_issue' THEN 'to_print' "
        "WHEN 'signed' THEN 'issued' "
        "WHEN 'submitted' THEN 'issued' "
        "ELSE status::text END"
        ")::request_status"
    )
    op.execute("ALTER TABLE requests ALTER COLUMN status SET DEFAULT 'draft'")
    op.execute("DROP TYPE request_status_new")

    # INV-2 в прежней редакции: issued ⟺ writeoff_id IS NOT NULL.
    op.create_check_constraint(
        "ck_requests_issued_iff_posted",
        "requests",
        "(status = 'issued') = (writeoff_id IS NOT NULL)",
    )
    # Прежний частичный индекс очереди «К печати».
    op.execute(
        "CREATE INDEX ix_requests_to_print ON requests (id) WHERE status = 'to_print'"
    )

    # ── §3. signature_batches ───────────────────────────────────────────
    op.drop_index("ix_signature_batches_created_by", table_name="signature_batches")
    op.drop_table("signature_batches")
