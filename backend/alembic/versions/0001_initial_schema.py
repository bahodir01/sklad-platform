"""initial schema: М1–М7, PostgreSQL 16

Схема утверждена и заморожена (02-contract.json — источник правды), поэтому
накатывается ЦЕЛИКОМ одной ревизией, а не дробится по этапам ТЗ §11: дробление
привело бы к тому, что контракт и БД расходились бы между этапами.

Содержит: 22 таблицы, 7 enum-типов, все CHECK и UNIQUE (INV-1…INV-9),
составной FK для INV-4, триггер SV-9, частичные индексы (AP-2/AP-3),
seed двух касс.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS = (
    "user_role",
    "user_category",
    "catalog_status",
    "notification_status",
    "request_status",
    "movement_doc_type",
    "cash_desk_type",
)

# Порядок создания: справочники → документы → writeoffs → requests →
# ledger → деньги → аудит. writeoffs строго ДО requests (requests.writeoff_id).
TABLES_IN_REVERSE = (
    "audit_log",
    "money_expense",
    "money_income",
    "cash_desks",
    "stock_balances",
    "stock_movements",
    "request_items",
    "requests",
    "writeoff_items",
    "writeoffs",
    "transfer_items",
    "transfers",
    "acquisition_items",
    "acquisitions",
    "notification_items",
    "notifications",
    "expense_categories",
    "expense_types",
    "warehouses",
    "products",
    "units",
    "users",
)

# ── SV-9: заявка только со склада списания ──────────────────────────
# Правило МОМЕНТА ПОДАЧИ: проверяется, когда заявка создаётся или когда ей
# меняют склад. Снятие галочки со склада НЕ инвалидирует уже поданные
# заявки — поэтому это триггер, а не FK на (id, allows_issuance).
# Область действия — ТОЛЬКО requests: порча/брак, приобретения и
# перемещения работают с любым складом (ТЗ §3).
SV9_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION trg_requests_check_issuance_warehouse()
RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_allows boolean;
    v_name   varchar(255);
BEGIN
    -- Склад не менялся → правило не применяем. Без этой ветки UPDATE,
    -- пришедший с warehouse_id в SET-списке (например, полнострочный
    -- UPDATE из ORM), уронил бы issue() у старой заявки, чей склад с тех
    -- пор потерял галочку, — то самое инвалидирование задним числом,
    -- которого ТЗ требует избежать.
    IF TG_OP = 'UPDATE' AND NEW.warehouse_id IS NOT DISTINCT FROM OLD.warehouse_id THEN
        RETURN NEW;
    END IF;

    SELECT allows_issuance, name INTO v_allows, v_name
      FROM warehouses WHERE id = NEW.warehouse_id;

    IF NOT v_allows THEN
        RAISE EXCEPTION
            'Склад "%" не является складом списания — заявка на него невозможна', v_name
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

# UPDATE OF warehouse_id: на переходах статусов (confirm/print/issue)
# триггер не срабатывает вовсе — они склад не трогают.
SV9_TRIGGER = """
CREATE TRIGGER requests_check_issuance_warehouse
    BEFORE INSERT OR UPDATE OF warehouse_id ON requests
    FOR EACH ROW
    EXECUTE FUNCTION trg_requests_check_issuance_warehouse()
"""


def upgrade() -> None:
    bind = op.get_bind()

    # ── enums ───────────────────────────────────────────────────────
    for enum in (
        postgresql.ENUM("admin", "teacher", "worker", name="user_role"),
        postgresql.ENUM("teacher", "worker", name="user_category"),
        postgresql.ENUM("active", "archived", name="catalog_status"),
        postgresql.ENUM("draft", "in_progress", "closed", name="notification_status"),
        postgresql.ENUM("draft", "to_print", "printed", "issued", name="request_status"),
        postgresql.ENUM("acquisition", "transfer", "writeoff", name="movement_doc_type"),
        postgresql.ENUM("teacher", "worker", name="cash_desk_type"),
    ):
        enum.create(bind, checkfirst=True)

    # Типы уже созданы выше: create_type=False, иначе create_table попытается
    # создать их повторно и упадёт с DuplicateObject.
    user_role = postgresql.ENUM(name="user_role", create_type=False)
    user_category = postgresql.ENUM(name="user_category", create_type=False)
    catalog_status = postgresql.ENUM(name="catalog_status", create_type=False)
    notification_status = postgresql.ENUM(name="notification_status", create_type=False)
    request_status = postgresql.ENUM(name="request_status", create_type=False)
    movement_doc_type = postgresql.ENUM(name="movement_doc_type", create_type=False)
    cash_desk_type = postgresql.ENUM(name="cash_desk_type", create_type=False)

    # ═══════════════ М1. Справочники ════════════════════════════════
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("username", sa.String(150), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),  # Argon2id
        sa.Column("role", user_role, nullable=False),
        sa.Column("category", user_category, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "length(trim(full_name)) > 0", name="ck_users_full_name_not_blank"
        ),
        # INV-9: category IS NULL ⟺ role = 'admin'
        sa.CheckConstraint(
            "(category IS NULL) = (role = 'admin')", name="ck_users_category_iff_admin"
        ),
    )
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "units",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("sku", sa.String(64), nullable=True),
        sa.Column(
            "status", catalog_status, nullable=False, server_default=sa.text("'active'")
        ),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),  # SV-8
    )
    op.create_index("ix_products_unit_id", "products", ["unit_id"])
    op.create_index("ix_products_status", "products", ["status"])

    op.create_table(
        "warehouses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        # SV-9 / ОВ-5: «Склад списания». Отмеченных складов может быть НЕСКОЛЬКО —
        # частичного уникального индекса здесь быть не должно.
        sa.Column(
            "allows_issuance", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "status", catalog_status, nullable=False, server_default=sa.text("'active'")
        ),
    )
    op.create_index("ix_warehouses_status", "warehouses", ["status"])
    # AP-12: индекс по allows_issuance НЕ создаётся — справочник крошечный,
    # планировщик возьмёт seq scan и будет прав.

    op.create_table(  # расход ТОВАРА
        "expense_types",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("requires_employee", sa.Boolean(), nullable=False),
        sa.Column(
            "status", catalog_status, nullable=False, server_default=sa.text("'active'")
        ),
        # INV-4: целевой ключ составного FK из writeoffs
        sa.UniqueConstraint(
            "id", "requires_employee", name="uq_expense_types_id_requires_employee"
        ),
    )

    op.create_table(  # расход ДЕНЕГ
        "expense_categories",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "status", catalog_status, nullable=False, server_default=sa.text("'active'")
        ),
    )

    # ═══════════ М2. Документооборот товаров ════════════════════════
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("number", sa.String(32), nullable=False, unique=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", notification_status, nullable=False, server_default=sa.text("'draft'")
        ),
        sa.Column("comment", sa.Text(), nullable=True),  # бланк: Ehtiyojning asoslanishi
        # ── Печатная форма BILDIRISHNOMA (уточнение заказчика 17.07.2026) ──
        sa.Column("body_text", sa.Text(), nullable=False),  # абзац-обращение
        sa.Column("division_name", sa.String(255), nullable=False),  # Bo‘linma nomi
        sa.Column("pdf_url", sa.String(500), nullable=True),  # снимок бланка в MinIO
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "length(trim(body_text)) > 0", name="ck_notifications_body_text_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(division_name)) > 0", name="ck_notifications_division_name_not_blank"
        ),
    )
    op.create_index("ix_notifications_author_id", "notifications", ["author_id"])
    op.create_index("ix_notifications_warehouse_id", "notifications", ["warehouse_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.execute("CREATE INDEX ix_notifications_date ON notifications (date DESC)")

    op.create_table(
        "notification_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("qty_requested", sa.Numeric(14, 3), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(  # INV-6
            "qty_requested > 0", name="ck_notification_items_qty_positive"
        ),
        # AP-6/AP-7 агрегируют по (notification_id, product_id)
        sa.UniqueConstraint(
            "notification_id",
            "product_id",
            name="uq_notification_items_notification_product",
        ),
    )
    op.create_index(
        "ix_notification_items_notification_id", "notification_items", ["notification_id"]
    )
    op.create_index("ix_notification_items_product_id", "notification_items", ["product_id"])

    op.create_table(
        "acquisitions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("number", sa.String(32), nullable=False, unique=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier", sa.String(255), nullable=True),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_acquisitions_notification_id", "acquisitions", ["notification_id"])
    op.create_index("ix_acquisitions_warehouse_id", "acquisitions", ["warehouse_id"])
    op.create_index("ix_acquisitions_author_id", "acquisitions", ["author_id"])
    op.execute("CREATE INDEX ix_acquisitions_date ON acquisitions (date DESC)")

    op.create_table(
        "acquisition_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("acquisition_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.Numeric(14, 3), nullable=False),
        sa.Column("price", sa.Numeric(18, 2), nullable=True),
        sa.ForeignKeyConstraint(["acquisition_id"], ["acquisitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("qty > 0", name="ck_acquisition_items_qty_positive"),  # INV-6
        sa.CheckConstraint(
            "price IS NULL OR price >= 0", name="ck_acquisition_items_price_non_negative"
        ),
    )
    op.create_index(
        "ix_acquisition_items_acquisition_id", "acquisition_items", ["acquisition_id"]
    )
    op.create_index("ix_acquisition_items_product_id", "acquisition_items", ["product_id"])

    op.create_table(
        "transfers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("number", sa.String(32), nullable=False, unique=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("from_warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("to_warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["to_warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(  # INV-5
            "from_warehouse_id <> to_warehouse_id", name="ck_transfers_different_warehouses"
        ),
    )
    op.create_index("ix_transfers_from_warehouse_id", "transfers", ["from_warehouse_id"])
    op.create_index("ix_transfers_to_warehouse_id", "transfers", ["to_warehouse_id"])
    op.create_index("ix_transfers_author_id", "transfers", ["author_id"])
    op.execute("CREATE INDEX ix_transfers_date ON transfers (date DESC)")

    op.create_table(
        "transfer_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("transfer_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.Numeric(14, 3), nullable=False),
        sa.ForeignKeyConstraint(["transfer_id"], ["transfers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("qty > 0", name="ck_transfer_items_qty_positive"),  # INV-6
    )
    op.create_index("ix_transfer_items_transfer_id", "transfer_items", ["transfer_id"])
    op.create_index("ix_transfer_items_product_id", "transfer_items", ["product_id"])

    # ═══ М4. Расход товара (проводка) — строго ДО requests ═══════════
    # requests.writeoff_id ссылается на writeoffs; обратной ссылки нет,
    # поэтому цикла FK не возникает.
    op.create_table(
        "writeoffs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("number", sa.String(32), nullable=False, unique=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("expense_type_id", sa.BigInteger(), nullable=False),
        # Д-2: копия флага, синхронизируется составным FK
        sa.Column("requires_employee", sa.Boolean(), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=True),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        # INV-4, часть 1: копия флага не может разойтись со справочником.
        # ON UPDATE CASCADE — переключение requires_employee у типа расхода
        # автоматически протянется в проводки.
        sa.ForeignKeyConstraint(
            ["expense_type_id", "requires_employee"],
            ["expense_types.id", "expense_types.requires_employee"],
            name="fk_writeoffs_expense_type",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        # INV-4, часть 2: правило локально для строки → выражается CHECK-ом.
        # «Выдача» ⇒ сотрудник обязателен; «Порча»/«Брак» ⇒ сотрудник запрещён.
        sa.CheckConstraint(
            "(employee_id IS NOT NULL) = requires_employee",
            name="ck_writeoffs_employee_iff_required",
        ),
    )
    op.create_index("ix_writeoffs_warehouse_id", "writeoffs", ["warehouse_id"])
    op.create_index("ix_writeoffs_expense_type_id", "writeoffs", ["expense_type_id"])
    op.create_index("ix_writeoffs_employee_id", "writeoffs", ["employee_id"])
    op.create_index("ix_writeoffs_author_id", "writeoffs", ["author_id"])
    op.execute("CREATE INDEX ix_writeoffs_date ON writeoffs (date DESC)")

    op.create_table(
        "writeoff_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("writeoff_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.Numeric(14, 3), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["writeoff_id"], ["writeoffs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("qty > 0", name="ck_writeoff_items_qty_positive"),  # INV-6
    )
    op.create_index("ix_writeoff_items_writeoff_id", "writeoff_items", ["writeoff_id"])
    op.create_index("ix_writeoff_items_product_id", "writeoff_items", ["product_id"])

    # ═══════════ М4. Заявка (документ-основание) ════════════════════
    op.create_table(
        "requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # ADR-2a: именно этот номер печатается на бумажном бланке
        sa.Column("number", sa.String(32), nullable=False, unique=True),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status", request_status, nullable=False, server_default=sa.text("'draft'")
        ),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("writeoff_id", sa.BigInteger(), nullable=True),
        sa.Column("pdf_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["writeoff_id"], ["writeoffs.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_requests_reason_not_blank"),
        # INV-2 — ГЛАВНАЯ защита модели ADR-2: выдана ⟺ есть проводка
        sa.CheckConstraint(
            "(status = 'issued') = (writeoff_id IS NOT NULL)",
            name="ck_requests_issued_iff_posted",
        ),
        # INV-3: одна проводка не принадлежит двум заявкам
        sa.UniqueConstraint("writeoff_id", name="uq_requests_writeoff_id"),
    )
    # AP-2 + AP-3: очередь «К печати» и бейдж-счётчик. Частичный индекс:
    # содержит только строки to_print, поэтому COUNT каждые 30 сек читает
    # index-only несколько страниц вместо миллионов строк.
    op.execute("CREATE INDEX ix_requests_to_print ON requests (id) WHERE status = 'to_print'")
    op.execute(
        "CREATE INDEX ix_requests_employee_created "
        "ON requests (employee_id, created_at DESC)"  # AP-4
    )
    op.create_index("ix_requests_warehouse_id", "requests", ["warehouse_id"])
    op.create_index("ix_requests_status", "requests", ["status"])
    # AP-11 (проводка → заявка → бумага) покрыт UNIQUE-индексом
    # uq_requests_writeoff_id — отдельный индекс был бы дублем (О-2).

    op.create_table(
        "request_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.Numeric(14, 3), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("qty > 0", name="ck_request_items_qty_positive"),  # INV-6
    )
    op.create_index("ix_request_items_request_id", "request_items", ["request_id"])
    op.create_index("ix_request_items_product_id", "request_items", ["product_id"])

    # SV-9: триггер создаётся ПОСЛЕ requests.
    op.execute(SV9_TRIGGER_FUNCTION)
    op.execute(SV9_TRIGGER)

    # ═══════════════ М3. Ядро учёта ═════════════════════════════════
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        # СО ЗНАКОМ: + приход, − расход
        sa.Column("qty", sa.Numeric(14, 3), nullable=False),
        sa.Column("doc_type", movement_doc_type, nullable=False),
        # Д-3: полиморфная ссылка, FK намеренно нет
        sa.Column("doc_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        # CHECK (qty > 0) здесь НЕВОЗМОЖЕН: поле знаковое. Запрещаем лишь
        # пустое движение (О-6 — не «чинить» на > 0).
        sa.CheckConstraint("qty <> 0", name="ck_stock_movements_qty_non_zero"),
    )
    # AP-5: история движений, keyset-пагинация по (created_at, id)
    op.execute(
        "CREATE INDEX ix_stock_movements_product_wh_created ON stock_movements "
        "(product_id, warehouse_id, created_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_stock_movements_wh_created ON stock_movements "
        "(warehouse_id, created_at DESC, id DESC)"
    )
    op.create_index("ix_stock_movements_doc", "stock_movements", ["doc_type", "doc_id"])

    op.create_table(
        "stock_balances",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.Numeric(14, 3), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        # INV-1: последний рубеж против ухода остатка в минус
        sa.CheckConstraint("qty >= 0", name="ck_stock_balances_qty_non_negative"),
        # AP-1: точечный поиск (product, warehouse) + FOR UPDATE
        sa.UniqueConstraint(
            "product_id", "warehouse_id", name="uq_stock_balances_product_warehouse"
        ),
    )
    # AP-10: отчёт «остатки по складам» — обход в порядке склад → товар
    op.create_index(
        "ix_stock_balances_warehouse_product", "stock_balances", ["warehouse_id", "product_id"]
    )

    # ═══════════════ М5. Кассы и деньги ═════════════════════════════
    op.create_table(
        "cash_desks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("type", cash_desk_type, nullable=False, unique=True),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        # INV-8 — ОВ-2 ЗАКРЫТ заказчиком 17.07.2026: жёсткая блокировка.
        # Флага CASH_OVERDRAFT_MODE нет: CHECK живёт в БД и приложением
        # не обходится (02-database.md §7.4).
        sa.CheckConstraint("balance >= 0", name="ck_cash_desks_balance_non_negative"),
    )

    op.create_table(
        "money_income",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("cash_desk_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["cash_desk_id"], ["cash_desks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("amount > 0", name="ck_money_income_amount_positive"),
    )
    op.execute(
        "CREATE INDEX ix_money_income_cash_desk_date ON money_income (cash_desk_id, date DESC)"
    )
    op.create_index("ix_money_income_author_id", "money_income", ["author_id"])

    op.create_table(
        "money_expense",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # SV-6: кассу ставит сервер из users.category
        sa.Column("cash_desk_id", sa.BigInteger(), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("expense_category_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("receipt_url", sa.String(500), nullable=False),  # INV-7
        sa.Column("date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["cash_desk_id"], ["cash_desks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["expense_category_id"], ["expense_categories.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("amount > 0", name="ck_money_expense_amount_positive"),
        sa.CheckConstraint(
            "length(trim(description)) > 0", name="ck_money_expense_description_not_blank"
        ),
        # INV-7: без этого CHECK пустая строка '' обойдёт NOT NULL и чек станет фикцией
        sa.CheckConstraint(
            "length(trim(receipt_url)) > 0", name="ck_money_expense_receipt_not_blank"
        ),
    )
    # AP-8: отчёт ДДС, фильтр по категории обязателен
    op.execute(
        "CREATE INDEX ix_money_expense_category_date "
        "ON money_expense (expense_category_id, date DESC)"
    )
    op.execute(
        "CREATE INDEX ix_money_expense_cash_desk_date "
        "ON money_expense (cash_desk_id, date DESC)"
    )
    op.execute(
        "CREATE INDEX ix_money_expense_employee_date "
        "ON money_expense (employee_id, date DESC)"
    )

    # ═══════════════════ М7. Аудит ══════════════════════════════════
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("payload_diff", postgresql.JSONB(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity", "entity_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.execute("CREATE INDEX ix_audit_log_created_at ON audit_log (created_at DESC)")

    # ═════════════ seed: ровно две кассы (ТЗ §3 М5) ═════════════════
    # Кассы не создаются через API: их ровно две, type UNIQUE это закрепляет.
    op.execute("INSERT INTO cash_desks (type, balance) VALUES ('teacher', 0), ('worker', 0)")


def downgrade() -> None:
    # Триггер — до таблиц: DROP TABLE requests снял бы триггер, но функция
    # осталась бы висеть в схеме и повторный upgrade упал бы на
    # CREATE OR REPLACE с изменённой сигнатурой.
    op.execute("DROP TRIGGER IF EXISTS requests_check_issuance_warehouse ON requests")
    op.execute("DROP FUNCTION IF EXISTS trg_requests_check_issuance_warehouse()")

    # Таблицы — в обратном порядке зависимостей.
    for table in TABLES_IN_REVERSE:
        op.drop_table(table)

    # Enum-типы живут отдельно от таблиц: если их не снять, повторный
    # upgrade упадёт с DuplicateObject: type "user_role" already exists.
    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")  # noqa: S608
