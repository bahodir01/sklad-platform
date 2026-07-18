# -*- coding: utf-8 -*-
"""ИСТОЧНИК ПРАВДЫ СЛОВАРЯ ДАННЫХ. Правки вносятся ЗДЕСЬ и только здесь.

Собирает ОБА артефакта из ОДНОГО списка строк-атрибутов, одним вызовом
`build_all(rows, xlsx_path, contract_path)`:

    .feature-dev/02-data-dictionary.xlsx   — человекочитаемый словарь
    .feature-dev/02-contract.json          — машинный контракт для всех агентов

Запуск из корня проекта, без аргументов:

    python .feature-dev/build_dictionary.py

═══════════════════════════════════════════════════════════════════════════
  .xlsx и .json РУКАМИ НЕ ПРАВИТЬ.
═══════════════════════════════════════════════════════════════════════════
Оба файла — генерируемые артефакты и перезаписываются при каждом запуске.
Ручная правка любого из них ломает единственную гарантию, ради которой
здесь всё и устроено: Excel для людей и JSON для машин собраны из одного
списка `rows` и потому физически не могут разойтись. Правка в одном файле
её разрушает молча — расхождение всплывёт этажом ниже, у backend-, frontend-
или QA-агента, который читает контракт как истину.

Порядок внесения изменения:
  1. поправить нужный `A(...)` в этом файле;
  2. `python .feature-dev/build_dictionary.py`;
  3. прогнать гейт (см. ниже) — он обязан быть зелёным;
  4. закоммитить скрипт и оба перегенерированных артефакта вместе.

Проверка кода против контракта (ожидается exit 0):

    python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py \
        .feature-dev/02-contract.json backend/app/modules/*/models.py \
        backend/app/core/audit.py backend/app/modules/*/schemas.py

Стек: PostgreSQL 16 + SQLAlchemy 2.0 + Alembic + Pydantic v2 (НЕ Django).
Колонки BACKEND несут SQLAlchemy-семантику (ТЗ §0):
  be_type -> тип колонки SQLAlchemy; be_nullable -> nullable=; be_unique -> unique=;
  be_db_index -> index=; be_on_delete -> ondelete= в ForeignKey;
  be_choice_enum -> Python Enum + SAEnum; be_default -> default= / server_default=.

Проект greenfield: legacy-миграции нет, у всех строк old_table_attr = "🆕"
(в контракте legacy.is_new = true).
"""
import sys
from pathlib import Path

# Пути считаются от расположения файла, а не от cwd, — чтобы скрипт
# запускался из корня проекта без аргументов и не зависел от того,
# откуда его позвали.
FEATURE_DEV = Path(__file__).resolve().parent
PROJECT_ROOT = FEATURE_DEV.parent
SKILL = PROJECT_ROOT / ".claude" / "skills" / "database-schema-design" / "assets"
sys.path.insert(0, str(SKILL))

from data_dictionary_generator import Attribute, build_all  # noqa: E402

Y, N = "✓", "—"
rows = []


def A(table, attribute, **kw):
    kw.setdefault("status", "review")
    kw.setdefault("checked", "")
    kw.setdefault("old_table_attr", "🆕")   # greenfield: every attribute is new
    rows.append(Attribute(table=table, attribute=attribute, **kw))


def pk(table, doc, label="ID"):
    A(table, "id", doc=doc, label=label, new_type="bigserial",
      description="Суррогатный первичный ключ.",
      be_type="BigInteger", be_auto="autoincrement (Identity)", be_unique="True",
      be_nullable="False", be_db_index="True (PK)", be_editable="False",
      be_other="PRIMARY KEY", be_filter="id",
      fe_table_view=N, fe_input_type="number", fe_required="False", fe_disabled="True",
      api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)


# ══════════════════════════════════════════════════════════════════════════
# М1. СПРАВОЧНИКИ (НСИ)
# ══════════════════════════════════════════════════════════════════════════
D = "ТЗ §3 М1"

# ---- users ----
pk("users", D)
A("users", "full_name", doc=D, label="ФИО", new_type="varchar(255)",
  description="Полное имя сотрудника.",
  be_type="String(255)", be_nullable="False", be_other="CHECK (length(trim(full_name)) > 0)",
  be_filter="full_name__icontains",
  fe_table_view=Y, fe_input_type="text", fe_required="True", fe_max="255",
  fe_validations="required; trim; 1..255",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("users", "username", doc=D, label="Логин", new_type="varchar(150)",
  description="Логин для входа. Уникален по системе.",
  be_type="String(150)", be_unique="True", be_nullable="False", be_db_index="True (UNIQUE)",
  be_filter="username",
  fe_table_view=Y, fe_input_type="text", fe_required="True", fe_max="150",
  fe_validations="required; unique (async check); 3..150; без пробелов",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N,
  comments="Смена логина не предусмотрена API §6 (auth).")
A("users", "password_hash", doc=D + " · §7 Безопасность", label="Хеш пароля", new_type="varchar(255)",
  description="Argon2id-хеш. НИКОГДА не отдаётся наружу.",
  be_type="String(255)", be_nullable="False", be_editable="False",
  fe_table_view=N, fe_input_type="password", fe_required="True",
  fe_validations="на вход принимается plain password, хеш считает сервер",
  comments="В API отсутствует во всех схемах. Pydantic: поле только в UserCreate как password, в Read не выводится.",
  api_get_index=N, api_get_single=N, api_create=N, api_update=N)
A("users", "role", doc=D, label="Роль", new_type="enum",
  description="Роль RBAC: admin | teacher | worker.",
  be_type="SAEnum(UserRole, name='user_role')", be_choice_model="UserRole(str, Enum)",
  be_choice_enum="admin | teacher | worker", be_nullable="False", be_db_index="True",
  be_other="INV-9: CHECK ((category IS NULL) = (role = 'admin'))", be_filter="role",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_enum="admin | teacher | worker",
  fe_validations="required; при role=admin поле category скрывается и обнуляется",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("users", "category", doc=D, label="Категория (касса)", new_type="enum NULL",
  description="Категория сотрудника; определяет кассу (SV-6). NULL только для admin.",
  be_type="SAEnum(UserCategory, name='user_category')", be_choice_model="UserCategory(str, Enum)",
  be_choice_enum="teacher | worker", be_nullable="True",
  be_other="INV-9: CHECK ((category IS NULL) = (role = 'admin'))", be_filter="category",
  fe_table_view=Y, fe_input_type="select", fe_required="False",
  fe_choice_enum="teacher | worker",
  fe_validations="обязательно, если role != admin; запрещено, если role = admin",
  comments="SV-6: касса выводится сервером из этого поля, клиент кассу не присылает.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("users", "is_active", doc=D, label="Активен", new_type="boolean",
  description="Мягкое отключение учётной записи (физическое удаление запрещено, SV-8).",
  be_type="Boolean", be_nullable="False", be_default="True (server_default=true)", be_filter="is_active",
  fe_table_view=Y, fe_input_type="checkbox", fe_required="False", fe_default="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=Y)
A("users", "created_at", doc=D, label="Создан", new_type="timestamptz",
  description="Момент создания учётной записи.",
  be_type="DateTime(timezone=True)", be_auto="server_default=func.now() (аналог auto_now_add)",
  be_nullable="False", be_default="now()", be_editable="False", be_filter="created_at__range",
  fe_table_view=N, fe_input_type="date", fe_required="False", fe_disabled="True",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)

# ---- units ----
D = "ТЗ §3 М1 units"
pk("units", D)
A("units", "code", doc=D, label="Код ЕИ", new_type="varchar(16)",
  description="Краткий код единицы измерения: шт, кг, л, м.",
  be_type="String(16)", be_unique="True", be_nullable="False", be_db_index="True (UNIQUE)",
  be_filter="code",
  fe_table_view=Y, fe_input_type="text", fe_required="True", fe_max="16",
  fe_validations="required; unique; 1..16",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("units", "name", doc=D, label="Наименование ЕИ", new_type="varchar(100)",
  description="Полное название единицы измерения.",
  be_type="String(100)", be_nullable="False",
  fe_table_view=Y, fe_input_type="text", fe_required="True", fe_max="100",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("units", "is_active", doc=D, label="Активна", new_type="boolean",
  description="Мягкая архивация справочника (SV-8: физического удаления нет).",
  be_type="Boolean", be_nullable="False", be_default="True (server_default=true)", be_filter="is_active",
  fe_table_view=Y, fe_input_type="checkbox", fe_required="False", fe_default="True",
  comments="ТЗ §3.1 задаёт для units именно boolean is_active, а не enum status — сохранено дословно.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=Y)

# ---- products ----
D = "ТЗ §3 М1 products"
pk("products", D)
A("products", "name", doc=D, label="Номенклатура", new_type="varchar(255)",
  description="Наименование товара.",
  be_type="String(255)", be_nullable="False",
  be_filter="name__icontains",
  fe_table_view=Y, fe_input_type="text", fe_required="True", fe_max="255",
  comments="Индекса НЕТ (решение владельца контракта). В §4 ТЗ нет access pattern на поиск товара по названию; номенклатура — сотни позиций, ILIKE отрабатывает мгновенно; trgm потребовал бы расширения pg_trgm — нагрузка на эксплуатацию ради неизмеренной нужды. Правило проекта: индексы привязаны к заявленным access patterns. Добавить по факту замера, если появится требование. be_filter — это фильтр API, не индекс.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("products", "unit_id", doc=D, label="Единица измерения", new_type="bigint FK",
  description="Единица измерения товара. Строки документов ЕИ не хранят — берут отсюда.",
  be_type="BigInteger · ForeignKey('units.id', ondelete='RESTRICT')",
  be_choice_model="relationship Unit", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_filter="unit_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /units?is_active=true", fe_disabled="True (при update)",
  fe_validations="required; выбор только из активных ЕИ",
  comments="update=— : смена ЕИ у товара с историей движений переинтерпретировала бы уже проведённые количества.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("products", "sku", doc=D, label="Артикул", new_type="varchar(64) NULL",
  description="Артикул/код товара. Необязателен.",
  be_type="String(64)", be_nullable="True", be_filter="sku",
  fe_table_view=Y, fe_input_type="text", fe_required="False", fe_max="64",
  comments="ТЗ UNIQUE не требует — не навязываем: пустой артикул допустим и возможны дубли у разных поставщиков.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("products", "status", doc=D, label="Статус", new_type="enum",
  description="active | archived. Архивация вместо удаления (SV-8).",
  be_type="SAEnum(CatalogStatus, name='catalog_status')", be_choice_model="CatalogStatus(str, Enum)",
  be_choice_enum="active | archived", be_nullable="False",
  be_default="active (server_default='active')", be_db_index="True", be_filter="status",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_default="active",
  fe_choice_enum="active | archived",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=Y)

# ---- warehouses ----
D = "ТЗ §3 М1 warehouses"
pk("warehouses", D)
A("warehouses", "code", doc=D, label="Код склада", new_type="varchar(32)",
  description="Уникальный код склада.",
  be_type="String(32)", be_unique="True", be_nullable="False", be_db_index="True (UNIQUE)",
  be_filter="code",
  fe_table_view=Y, fe_input_type="text", fe_required="True", fe_max="32",
  fe_validations="required; unique",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("warehouses", "name", doc=D, label="Наименование склада", new_type="varchar(255)",
  description="Название склада.",
  be_type="String(255)", be_nullable="False", be_filter="name__icontains",
  fe_table_view=Y, fe_input_type="text", fe_required="True", fe_max="255",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("warehouses", "address", doc=D, label="Адрес", new_type="varchar(500) NULL",
  description="Физический адрес склада.",
  be_type="String(500)", be_nullable="True",
  fe_table_view=N, fe_input_type="text", fe_required="False", fe_max="500",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=Y)
A("warehouses", "allows_issuance", doc=D + " · SV-9 · AP-12 · ОВ-5", label="Склад списания", new_type="boolean",
  description="Галочка «Склад списания». Сотрудник может подать заявку только со склада с этим признаком (SV-9). Отмеченных складов может быть несколько.",
  be_type="Boolean", be_nullable="False", be_default="False (server_default=false)",
  be_other="SV-9: BEFORE INSERT OR UPDATE OF warehouse_id триггер на requests (НЕ составной FK — см. 02-database.md §7.3)",
  be_filter="allows_issuance",
  fe_table_view=Y, fe_input_type="checkbox", fe_required="False", fe_default="False",
  fe_validations="AP-12: список складов в форме заявки фильтруется allows_issuance=true AND status='active'",
  comments="ОВ-5 ЗАКРЫТ заказчиком 17.07.2026. Ограничение действует ТОЛЬКО на requests: порча/брак, приобретения и перемещения работают с любым складом — товар может испортиться где угодно, и если списать его будет негде, он навечно зависнет в остатках.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("warehouses", "status", doc=D, label="Статус", new_type="enum",
  description="active | archived (SV-8).",
  be_type="SAEnum(CatalogStatus, name='catalog_status')", be_choice_model="CatalogStatus(str, Enum)",
  be_choice_enum="active | archived", be_nullable="False",
  be_default="active (server_default='active')", be_db_index="True", be_filter="status",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_default="active",
  fe_choice_enum="active | archived",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=Y)

# ---- expense_types (расход ТОВАРА) ----
D = "ТЗ §3 М1 expense_types"
pk("expense_types", D)
A("expense_types", "name", doc=D, label="Тип расхода товара", new_type="varchar(100)",
  description="Выдача сотруднику / Порча / Брак.",
  be_type="String(100)", be_nullable="False", be_filter="name__icontains",
  fe_table_view=Y, fe_input_type="text", fe_required="True", fe_max="100",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("expense_types", "requires_employee", doc=D + " · INV-4", label="Требует сотрудника", new_type="boolean",
  description="Признак: при этом типе расхода сотрудник-получатель обязателен (Выдача) или запрещён (Порча/Брак).",
  be_type="Boolean", be_nullable="False", be_db_index="True (в составе UNIQUE(id, requires_employee))",
  be_other="INV-4: UNIQUE (id, requires_employee) — целевой ключ составного FK из writeoffs",
  be_filter="requires_employee",
  fe_table_view=Y, fe_input_type="checkbox", fe_required="True",
  fe_disabled="True (при update, если по типу есть проводки)",
  comments="INV-4 реализован составным FK writeoffs(expense_type_id, requires_employee) -> expense_types(id, requires_employee) ON UPDATE CASCADE. Поэтому здесь нужен UNIQUE(id, requires_employee).",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("expense_types", "status", doc=D, label="Статус", new_type="enum",
  description="active | archived (SV-8).",
  be_type="SAEnum(CatalogStatus, name='catalog_status')", be_choice_model="CatalogStatus(str, Enum)",
  be_choice_enum="active | archived", be_nullable="False",
  be_default="active (server_default='active')", be_filter="status",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_default="active",
  fe_choice_enum="active | archived",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=Y)

# ---- expense_categories (расход ДЕНЕГ) ----
D = "ТЗ §3 М1 expense_categories"
pk("expense_categories", D)
A("expense_categories", "name", doc=D, label="Вид расхода денег", new_type="varchar(100)",
  description="Канцелярия, Хознужды и т.п. НЕ путать с expense_types (расход товара).",
  be_type="String(100)", be_nullable="False", be_filter="name__icontains",
  fe_table_view=Y, fe_input_type="text", fe_required="True", fe_max="100",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=Y)
A("expense_categories", "status", doc=D, label="Статус", new_type="enum",
  description="active | archived (SV-8).",
  be_type="SAEnum(CatalogStatus, name='catalog_status')", be_choice_model="CatalogStatus(str, Enum)",
  be_choice_enum="active | archived", be_nullable="False",
  be_default="active (server_default='active')", be_filter="status",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_default="active",
  fe_choice_enum="active | archived",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=Y)

# ══════════════════════════════════════════════════════════════════════════
# М2. ДОКУМЕНТООБОРОТ ТОВАРОВ
# ══════════════════════════════════════════════════════════════════════════
D = "ТЗ §3 М2 notifications"
pk("notifications", D)
A("notifications", "number", doc=D, label="Номер уведомления", new_type="varchar(32)",
  description="Автономер, независимая серия (shared/numbering.py).",
  be_type="String(32)", be_unique="True", be_nullable="False", be_db_index="True (UNIQUE)",
  be_editable="False", be_filter="number",
  fe_table_view=Y, fe_input_type="text", fe_required="False", fe_max="32", fe_disabled="True",
  comments="Генерируется сервером, клиент не присылает.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("notifications", "date", doc=D, label="Дата", new_type="date",
  description="Дата документа.",
  be_type="Date", be_nullable="False", be_db_index="True", be_filter="date__range",
  fe_table_view=Y, fe_input_type="date", fe_required="True",
  fe_validations="required; локальный формат ДД.ММ.ГГГГ",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("notifications", "author_id", doc=D, label="Автор", new_type="bigint FK",
  description="Кто создал уведомление. Проставляется сервером из текущего пользователя.",
  be_type="BigInteger · ForeignKey('users.id', ondelete='RESTRICT')",
  be_choice_model="relationship User", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_editable="False", be_filter="author_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  comments="Клиент не присылает: берётся из JWT.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("notifications", "warehouse_id", doc=D, label="Склад назначения", new_type="bigint FK",
  description="Склад, куда планируется поступление закупаемого товара.",
  be_type="BigInteger · ForeignKey('warehouses.id', ondelete='RESTRICT')",
  be_choice_model="relationship Warehouse", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_filter="warehouse_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /warehouses?status=active",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("notifications", "status", doc=D + " · SV-7", label="Статус", new_type="enum",
  description="draft | in_progress | closed. Автозакрытие при остатке 0 по всем строкам (SV-7).",
  be_type="SAEnum(NotificationStatus, name='notification_status')",
  be_choice_model="NotificationStatus(str, Enum)", be_choice_enum="draft | in_progress | closed",
  be_nullable="False", be_default="draft (server_default='draft')", be_db_index="True",
  be_editable="False", be_filter="status",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_default="draft",
  fe_choice_enum="draft | in_progress | closed", fe_disabled="True",
  comments="Статусом управляет сервис (SV-7), не клиент.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("notifications", "comment", doc=D + " · бланк BILDIRISHNOMA", label="Комментарий", new_type="text NULL",
  description="Произвольный комментарий к уведомлению. На бланке BILDIRISHNOMA печатается как «Ehtiyojning asoslanishi» (причина закупки).",
  be_type="Text", be_nullable="True",
  fe_table_view=N, fe_input_type="textarea", fe_required="False",
  comments="Существующая колонка закрывает «Ehtiyojning asoslanishi» бланка — отдельной колонки под причину НЕ заводим (решение заказчика 17.07.2026). В шаблон notification.html приходит под именем n.justification: имя переменной контекста рендера, не колонки.",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("notifications", "body_text", doc=D + " · бланк BILDIRISHNOMA", label="Текст обращения", new_type="text",
  description="Абзац-обращение бланка («Sizdan… so‘rayman:»). Тело документа, меняется в каждом уведомлении, пишет администратор.",
  be_type="Text", be_nullable="False",
  be_other="CHECK (length(trim(body_text)) > 0) — тело документа пустым быть не может; NOT NULL сам по себе допускает ''",
  fe_table_view=N, fe_input_type="textarea", fe_required="True",
  fe_validations="required; непустая строка",
  comments="Товары в текст абзаца НЕ дублируются — перечень рендерится из notification_items, иначе текст и таблица бланка разойдутся (см. notification.html).",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("notifications", "division_name", doc=D + " · бланк BILDIRISHNOMA", label="Наименование подразделения", new_type="varchar(255)",
  description="«Bo‘linma nomi» бланка — подразделение-инициатор потребности.",
  be_type="String(255)", be_nullable="False",
  be_other="CHECK (length(trim(division_name)) > 0)",
  fe_table_view=N, fe_input_type="text", fe_required="True", fe_max="255",
  fe_validations="required; trim; 1..255",
  comments="СВОБОДНЫЙ ТЕКСТ, не справочник и не FK на warehouses (решение заказчика 17.07.2026, пересмотру не подлежит). Подразделение и склад назначения — разные сущности: склад отвечает на «куда придёт товар», подразделение — «кто просит». Отдельной таблицы нет — 22 таблицы остаются 22.",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("notifications", "pdf_url", doc=D + " · бланк BILDIRISHNOMA", label="PDF бланка", new_type="varchar(500) NULL",
  description="Ключ объекта в MinIO (бакет documents) — снимок напечатанного бланка. Отдаётся presigned URL с TTL 5 мин.",
  be_type="String(500)", be_nullable="True", be_editable="False",
  fe_table_view=N, fe_input_type="text", fe_required="False", fe_max="500", fe_disabled="True",
  comments="Ставит сервер при рендере, клиент не присылает. Хранится ключ объекта, не публичная ссылка: бакет приватный (§7 Файлы). Печать НЕ меняет status и перепечатка безопасна: на бланке нет колонок «приобретено»/«остаток», только запрошенное количество, поэтому частичные закупки на документ не влияют.",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("notifications", "created_at", doc=D, label="Создано", new_type="timestamptz",
  description="Момент создания записи.",
  be_type="DateTime(timezone=True)", be_auto="server_default=func.now()",
  be_nullable="False", be_default="now()", be_editable="False", be_filter="created_at__range",
  fe_table_view=N, fe_input_type="date", fe_required="False", fe_disabled="True",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)

D = "ТЗ §3 М2 notification_items"
pk("notification_items", D)
A("notification_items", "notification_id", doc=D, label="Уведомление", new_type="bigint FK",
  description="Родительское уведомление. Строка не живёт без шапки.",
  be_type="BigInteger · ForeignKey('notifications.id', ondelete='CASCADE')",
  be_choice_model="relationship Notification", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="CASCADE", be_filter="notification_id",
  fe_table_view=N, fe_input_type="number", fe_required="False", fe_disabled="True",
  comments="AP-7: SELECT ... FOR UPDATE по этому ключу при контроле перезакупки (SV-1).",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("notification_items", "product_id", doc=D, label="Товар", new_type="bigint FK",
  description="Заявленный к закупке товар.",
  be_type="BigInteger · ForeignKey('products.id', ondelete='RESTRICT')",
  be_choice_model="relationship Product", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT",
  be_other="UNIQUE (notification_id, product_id) — AP-6/AP-7 агрегируют по этой паре",
  be_filter="product_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /products?status=active",
  fe_validations="required; товар не должен повторяться в строках одного уведомления",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("notification_items", "qty_requested", doc=D, label="Заявлено", new_type="numeric(14,3)",
  description="Заявленное количество. Дробное (кг, л). Потолок для контроля перезакупки (SV-1).",
  be_type="Numeric(14, 3)", be_nullable="False",
  be_other="INV-6: CHECK (qty_requested > 0)",
  fe_table_view=Y, fe_input_type="number", fe_required="True",
  fe_validations="required; > 0; до 3 знаков после запятой; ЕИ показывается из products.unit_id",
  comments="qty_purchased и «остаток к приобретению» НЕ хранятся — считаются из acquisition_items (ТЗ §3).",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)

D = "ТЗ §3 М2 acquisitions"
pk("acquisitions", D)
A("acquisitions", "number", doc=D, label="Номер приобретения", new_type="varchar(32)",
  description="Автономер, независимая серия.",
  be_type="String(32)", be_unique="True", be_nullable="False", be_db_index="True (UNIQUE)",
  be_editable="False", be_filter="number",
  fe_table_view=Y, fe_input_type="text", fe_required="False", fe_max="32", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("acquisitions", "date", doc=D, label="Дата", new_type="date",
  description="Дата приобретения (закупка частями в разные даты).",
  be_type="Date", be_nullable="False", be_db_index="True", be_filter="date__range",
  fe_table_view=Y, fe_input_type="date", fe_required="True",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("acquisitions", "notification_id", doc=D, label="Уведомление-основание", new_type="bigint FK",
  description="Уведомление, по которому идёт закупка. Одно уведомление → много приобретений.",
  be_type="BigInteger · ForeignKey('notifications.id', ondelete='RESTRICT')",
  be_choice_model="relationship Notification", be_nullable="False", be_db_index="True (FK, AP-6)",
  be_on_delete="RESTRICT", be_filter="notification_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /notifications?status=in_progress",
  comments="RESTRICT: уведомление с закупками не удаляется — иначе история приобретений теряет основание.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("acquisitions", "warehouse_id", doc=D, label="Склад поступления", new_type="bigint FK",
  description="Склад, на который приходуется товар (ledger.post +qty).",
  be_type="BigInteger · ForeignKey('warehouses.id', ondelete='RESTRICT')",
  be_choice_model="relationship Warehouse", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_filter="warehouse_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /warehouses?status=active",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("acquisitions", "supplier", doc=D + " · ОВ-4", label="Поставщик", new_type="varchar(255) NULL",
  description="Поставщик строкой. Отдельного справочника нет (ОВ-4).",
  be_type="String(255)", be_nullable="True", be_filter="supplier__icontains",
  fe_table_view=Y, fe_input_type="text", fe_required="False", fe_max="255",
  comments="ОВ-4: допущение — строка, не справочник. Таблица появится при интеграции с 1С.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("acquisitions", "author_id", doc=D, label="Автор", new_type="bigint FK",
  description="Кто провёл приобретение. Из JWT.",
  be_type="BigInteger · ForeignKey('users.id', ondelete='RESTRICT')",
  be_choice_model="relationship User", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_editable="False", be_filter="author_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)

D = "ТЗ §3 М2 acquisition_items"
pk("acquisition_items", D)
A("acquisition_items", "acquisition_id", doc=D, label="Приобретение", new_type="bigint FK",
  description="Родительский документ приобретения.",
  be_type="BigInteger · ForeignKey('acquisitions.id', ondelete='CASCADE')",
  be_choice_model="relationship Acquisition", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="CASCADE", be_filter="acquisition_id",
  fe_table_view=N, fe_input_type="number", fe_required="False", fe_disabled="True",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("acquisition_items", "product_id", doc=D, label="Товар", new_type="bigint FK",
  description="Приобретённый товар.",
  be_type="BigInteger · ForeignKey('products.id', ondelete='RESTRICT')",
  be_choice_model="relationship Product", be_nullable="False", be_db_index="True (FK, AP-6)",
  be_on_delete="RESTRICT", be_filter="product_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="строки связанного уведомления (GET /notifications/{id})",
  fe_validations="required; товар должен присутствовать в строках уведомления",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("acquisition_items", "qty", doc=D + " · SV-1", label="Количество", new_type="numeric(14,3)",
  description="Приобретённое количество. Источник расчёта qty_purchased и остатка к приобретению.",
  be_type="Numeric(14, 3)", be_nullable="False",
  be_other="INV-6: CHECK (qty > 0); SV-1: SUM(qty) ≤ notification_items.qty_requested (сервис, FOR UPDATE)",
  fe_table_view=Y, fe_input_type="number", fe_required="True",
  fe_validations="required; > 0; ≤ остатка к приобретению (сервер — истина, AP-7)",
  comments="AP-7: контроль перезакупки агрегирует именно это поле.",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("acquisition_items", "price", doc=D, label="Цена", new_type="numeric(18,2) NULL",
  description="Цена за единицу, UZS. Деньги — только NUMERIC.",
  be_type="Numeric(18, 2)", be_nullable="True",
  be_other="CHECK (price IS NULL OR price >= 0)",
  fe_table_view=Y, fe_input_type="number", fe_required="False",
  fe_validations="≥ 0; 2 знака; валюта UZS",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)

D = "ТЗ §3 М2 transfers"
pk("transfers", D)
A("transfers", "number", doc=D, label="Номер перемещения", new_type="varchar(32)",
  description="Автономер, независимая серия.",
  be_type="String(32)", be_unique="True", be_nullable="False", be_db_index="True (UNIQUE)",
  be_editable="False", be_filter="number",
  fe_table_view=Y, fe_input_type="text", fe_required="False", fe_max="32", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("transfers", "date", doc=D, label="Дата", new_type="date",
  description="Дата перемещения.",
  be_type="Date", be_nullable="False", be_db_index="True", be_filter="date__range",
  fe_table_view=Y, fe_input_type="date", fe_required="True",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("transfers", "from_warehouse_id", doc=D + " · INV-5", label="Склад-источник", new_type="bigint FK",
  description="Откуда перемещается товар (ledger.post −qty).",
  be_type="BigInteger · ForeignKey('warehouses.id', ondelete='RESTRICT')",
  be_choice_model="relationship Warehouse", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT",
  be_other="INV-5: CHECK (from_warehouse_id <> to_warehouse_id)", be_filter="from_warehouse_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /warehouses?status=active",
  fe_validations="required; не равен складу-получателю",
  comments="SV-3: перемещение больше остатка запрещено (FOR UPDATE на stock_balances).",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("transfers", "to_warehouse_id", doc=D + " · INV-5", label="Склад-получатель", new_type="bigint FK",
  description="Куда перемещается товар (ledger.post +qty).",
  be_type="BigInteger · ForeignKey('warehouses.id', ondelete='RESTRICT')",
  be_choice_model="relationship Warehouse", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT",
  be_other="INV-5: CHECK (from_warehouse_id <> to_warehouse_id)", be_filter="to_warehouse_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /warehouses?status=active",
  fe_validations="required; не равен складу-источнику",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("transfers", "author_id", doc=D, label="Автор", new_type="bigint FK",
  description="Кто провёл перемещение. Из JWT.",
  be_type="BigInteger · ForeignKey('users.id', ondelete='RESTRICT')",
  be_choice_model="relationship User", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_editable="False", be_filter="author_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)

D = "ТЗ §3 М2 transfer_items"
pk("transfer_items", D)
A("transfer_items", "transfer_id", doc=D, label="Перемещение", new_type="bigint FK",
  description="Родительский документ перемещения.",
  be_type="BigInteger · ForeignKey('transfers.id', ondelete='CASCADE')",
  be_choice_model="relationship Transfer", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="CASCADE", be_filter="transfer_id",
  fe_table_view=N, fe_input_type="number", fe_required="False", fe_disabled="True",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("transfer_items", "product_id", doc=D, label="Товар", new_type="bigint FK",
  description="Перемещаемый товар.",
  be_type="BigInteger · ForeignKey('products.id', ondelete='RESTRICT')",
  be_choice_model="relationship Product", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_filter="product_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /stock/balances?warehouse_id={from_warehouse_id}",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("transfer_items", "qty", doc=D, label="Количество", new_type="numeric(14,3)",
  description="Перемещаемое количество. Порождает ДВЕ записи в stock_movements (−/+).",
  be_type="Numeric(14, 3)", be_nullable="False",
  be_other="INV-6: CHECK (qty > 0); SV-3: ≤ остатка на складе-источнике (сервис)",
  fe_table_view=Y, fe_input_type="number", fe_required="True",
  fe_validations="required; > 0; ≤ остатка на складе-источнике (сервер — истина)",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)

# ══════════════════════════════════════════════════════════════════════════
# М3. СКЛАДСКОЙ УЧЁТ
# ══════════════════════════════════════════════════════════════════════════
D = "ТЗ §3 М3 stock_movements · ADR-1"
pk("stock_movements", D)
A("stock_movements", "product_id", doc=D, label="Товар", new_type="bigint FK",
  description="Товар движения.",
  be_type="BigInteger · ForeignKey('products.id', ondelete='RESTRICT')",
  be_choice_model="relationship Product", be_nullable="False",
  be_db_index="True (в составе AP-5 composite)", be_on_delete="RESTRICT",
  be_editable="False", be_filter="product_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  comments="Журнал append-only: пишет только stock/ledger.py (SV-2). API на запись нет.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("stock_movements", "warehouse_id", doc=D, label="Склад", new_type="bigint FK",
  description="Склад движения.",
  be_type="BigInteger · ForeignKey('warehouses.id', ondelete='RESTRICT')",
  be_choice_model="relationship Warehouse", be_nullable="False",
  be_db_index="True (в составе AP-5 composite)", be_on_delete="RESTRICT",
  be_editable="False", be_filter="warehouse_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("stock_movements", "qty", doc=D, label="Количество (со знаком)", new_type="numeric(14,3)",
  description="Приход +, расход −. Единственное поле со знаком в системе.",
  be_type="Numeric(14, 3)", be_nullable="False", be_editable="False",
  be_other="CHECK (qty <> 0) — движение нулевого объёма бессмысленно",
  fe_table_view=Y, fe_input_type="number", fe_required="False", fe_disabled="True",
  fe_validations="отображать со знаком и цветом: + приход, − расход",
  comments="ЗНАКОВОЕ поле: CHECK (qty > 0) здесь НЕЛЬЗЯ, в отличие от *_items (INV-6).",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("stock_movements", "doc_type", doc=D, label="Вид документа", new_type="enum",
  description="acquisition | transfer | writeoff — тип документа-основания.",
  be_type="SAEnum(MovementDocType, name='movement_doc_type')",
  be_choice_model="MovementDocType(str, Enum)", be_choice_enum="acquisition | transfer | writeoff",
  be_nullable="False", be_db_index="True (composite (doc_type, doc_id))",
  be_editable="False", be_filter="doc_type",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  fe_choice_enum="acquisition | transfer | writeoff",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("stock_movements", "doc_id", doc=D, label="ID документа-основания", new_type="bigint",
  description="Полиморфная ссылка на acquisitions/transfers/writeoffs — вместе с doc_type.",
  be_type="BigInteger", be_nullable="False",
  be_db_index="True (composite (doc_type, doc_id))", be_editable="False",
  be_other="FK НЕТ: ссылка полиморфная, целостность обеспечивает ledger.post() — единая точка записи (SV-2)",
  be_filter="doc_id",
  fe_table_view=N, fe_input_type="number", fe_required="False", fe_disabled="True",
  comments="Осознанный отказ от FK. Альтернатива (три nullable FK) даёт три пустые колонки на каждой строке горячей таблицы.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("stock_movements", "created_at", doc=D + " · AP-5", label="Момент проводки", new_type="timestamptz",
  description="Время движения. Ключ сортировки и keyset-пагинации истории (AP-5).",
  be_type="DateTime(timezone=True)", be_auto="server_default=func.now()",
  be_nullable="False", be_default="now()",
  be_db_index="True (composite ... created_at DESC, id DESC)", be_editable="False",
  be_filter="created_at__range",
  fe_table_view=Y, fe_input_type="date", fe_required="False", fe_disabled="True",
  comments="AP-5: keyset-курсор = (created_at, id) — id разрешает коллизии одинаковых меток времени.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)

D = "ТЗ §3 М3 stock_balances · ADR-1 · AP-1"
pk("stock_balances", D)
A("stock_balances", "product_id", doc=D, label="Товар", new_type="bigint FK",
  description="Товар остатка.",
  be_type="BigInteger · ForeignKey('products.id', ondelete='RESTRICT')",
  be_choice_model="relationship Product", be_nullable="False",
  be_db_index="True (UNIQUE (product_id, warehouse_id) — AP-1)", be_on_delete="RESTRICT",
  be_editable="False", be_filter="product_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  comments="ЕДИНСТВЕННАЯ денормализация в схеме. Обоснование — AP-1 (ADR-1).",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("stock_balances", "warehouse_id", doc=D, label="Склад", new_type="bigint FK",
  description="Склад остатка.",
  be_type="BigInteger · ForeignKey('warehouses.id', ondelete='RESTRICT')",
  be_choice_model="relationship Warehouse", be_nullable="False",
  be_db_index="True (UNIQUE (product_id, warehouse_id); + index (warehouse_id, product_id) — AP-10)",
  be_on_delete="RESTRICT", be_editable="False", be_filter="warehouse_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("stock_balances", "qty", doc=D + " · INV-1", label="Остаток", new_type="numeric(14,3)",
  description="Актуальный остаток = проекция SUM(stock_movements.qty). Прямое редактирование запрещено (SV-2).",
  be_type="Numeric(14, 3)", be_nullable="False", be_default="0 (server_default='0')",
  be_editable="False", be_other="INV-1: CHECK (qty >= 0) — последний рубеж против ухода в минус",
  fe_table_view=Y, fe_input_type="number", fe_required="False", fe_disabled="True",
  comments="AP-1: SELECT ... FOR UPDATE по (product_id, warehouse_id) сериализует конкурентные списания. Ночная задача reconcile_stock сверяет с журналом.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)

# ══════════════════════════════════════════════════════════════════════════
# М4. ЗАЯВКИ И ПЕЧАТЬ  +  РАСХОД ТОВАРА
# ══════════════════════════════════════════════════════════════════════════
D = "ТЗ §3 М4 requests · ADR-2"
pk("requests", D)
A("requests", "number", doc=D + " · ADR-2a", label="Номер заявки", new_type="varchar(32)",
  description="Своя серия. ИМЕННО ЭТОТ номер печатается на бумажном бланке (ADR-2a).",
  be_type="String(32)", be_unique="True", be_nullable="False", be_db_index="True (UNIQUE)",
  be_editable="False", be_filter="number",
  fe_table_view=Y, fe_input_type="text", fe_required="False", fe_max="32", fe_disabled="True",
  comments="ADR-2a: в момент печати writeoff ещё не существует, поэтому на бумаге физически может стоять только номер заявки. Реестр §6.4 показывает оба номера, поиск — по любому.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("requests", "employee_id", doc=D + " · AP-4", label="Сотрудник", new_type="bigint FK",
  description="Заявитель. Проставляется сервером из текущего пользователя.",
  be_type="BigInteger · ForeignKey('users.id', ondelete='RESTRICT')",
  be_choice_model="relationship User", be_nullable="False",
  be_db_index="True (composite (employee_id, created_at DESC) — AP-4)", be_on_delete="RESTRICT",
  be_editable="False", be_filter="employee_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  comments="AP-4 «Мои заявки». Row-level фильтр: сотрудник видит только свои (§1.3).",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("requests", "warehouse_id", doc=D + " · ОВ-5", label="Склад выдачи", new_type="bigint FK",
  description="Склад, с которого будет выдан товар.",
  be_type="BigInteger · ForeignKey('warehouses.id', ondelete='RESTRICT')",
  be_choice_model="relationship Warehouse", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_filter="warehouse_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /stock/balances (склады, где товар в наличии — ОВ-5)",
  comments="ОВ-5: допущение — выбор ограничен складами, где товар есть в наличии. Схему не меняет.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("requests", "reason", doc=D, label="Обоснование", new_type="text",
  description="Зачем сотруднику товар. Печатается на бланке.",
  be_type="Text", be_nullable="False", be_other="CHECK (length(trim(reason)) > 0)",
  fe_table_view=N, fe_input_type="textarea", fe_required="True",
  fe_validations="required; непустая строка",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("requests", "status", doc=D + " · AP-2/AP-3 · INV-2", label="Статус заявки", new_type="enum",
  description="draft | to_print | printed | issued. Статусы принадлежат ЗАЯВКЕ, не проводке (ADR-2).",
  be_type="SAEnum(RequestStatus, name='request_status')", be_choice_model="RequestStatus(str, Enum)",
  be_choice_enum="draft | to_print | printed | issued", be_nullable="False",
  be_default="draft (server_default='draft')",
  be_db_index="True (partial: WHERE status = 'to_print' — AP-2/AP-3)", be_editable="False",
  be_other="INV-2: CHECK ((status = 'issued') = (writeoff_id IS NOT NULL))", be_filter="status",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_default="draft",
  fe_choice_enum="draft | to_print | printed | issued", fe_disabled="True",
  comments="Переходы только через POST /confirm, /print, /issue. SV-5: issue() делает условный UPDATE ... WHERE status='printed'.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("requests", "printed_at", doc=D + " · ОВ-3", label="Напечатано", new_type="timestamptz NULL",
  description="Момент проставления статуса «Напечатан» (вручную завскладом, ОВ-3).",
  be_type="DateTime(timezone=True)", be_nullable="True", be_editable="False",
  be_other="CHECK (status IN ('draft','to_print')) = (printed_at IS NULL) не вводится: см. отчёт, ослабило бы повторную печать",
  be_filter="printed_at__range",
  fe_table_view=N, fe_input_type="date", fe_required="False", fe_disabled="True",
  comments="ОВ-3: допущение — статус ставит завскладом вручную, открытие PDF ≠ факт печати.",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("requests", "issued_at", doc=D, label="Выдано", new_type="timestamptz NULL",
  description="Момент выдачи товара сотруднику.",
  be_type="DateTime(timezone=True)", be_nullable="True", be_editable="False",
  be_filter="issued_at__range",
  fe_table_view=Y, fe_input_type="date", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("requests", "writeoff_id", doc=D + " · INV-2/INV-3 · AP-11", label="Проводка списания", new_type="bigint FK NULL UNIQUE",
  description="Ссылка на проводку. NULL до выдачи — заполняется ТОЛЬКО в момент issue() (ADR-2).",
  be_type="BigInteger · ForeignKey('writeoffs.id', ondelete='RESTRICT')",
  be_choice_model="relationship Writeoff (uselist=False)", be_unique="True", be_nullable="True",
  be_db_index="True (UNIQUE — покрывает AP-11: проводка → заявка → бумага)",
  be_on_delete="RESTRICT", be_editable="False",
  be_other="INV-2: CHECK ((status = 'issued') = (writeoff_id IS NOT NULL)); INV-3: UNIQUE (writeoff_id)",
  be_filter="writeoff_id",
  fe_table_view=Y, fe_input_type="number", fe_required="False", fe_disabled="True",
  comments="ГЛАВНАЯ защита модели ADR-2. Без INV-2 возможна заявка «Выдан» без проводки (товар отдали, учёт не знает) либо проводка без основания.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("requests", "pdf_url", doc=D, label="PDF бланка", new_type="varchar(500) NULL",
  description="Ключ объекта в MinIO (бакет documents). Отдаётся presigned URL с TTL 5 мин.",
  be_type="String(500)", be_nullable="True", be_editable="False",
  fe_table_view=N, fe_input_type="text", fe_required="False", fe_max="500", fe_disabled="True",
  comments="Хранится ключ объекта, не публичная ссылка: бакет приватный (§7 Файлы).",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("requests", "created_at", doc=D + " · AP-4", label="Создана", new_type="timestamptz",
  description="Фиксируется при подтверждении заявки. Ключ сортировки «Моих заявок» (AP-4).",
  be_type="DateTime(timezone=True)", be_auto="server_default=func.now()",
  be_nullable="False", be_default="now()",
  be_db_index="True (composite (employee_id, created_at DESC) — AP-4)", be_editable="False",
  be_filter="created_at__range",
  fe_table_view=Y, fe_input_type="date", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)

D = "ТЗ §3 М4 request_items"
pk("request_items", D)
A("request_items", "request_id", doc=D, label="Заявка", new_type="bigint FK",
  description="Родительская заявка.",
  be_type="BigInteger · ForeignKey('requests.id', ondelete='CASCADE')",
  be_choice_model="relationship Request", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="CASCADE", be_filter="request_id",
  fe_table_view=N, fe_input_type="number", fe_required="False", fe_disabled="True",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("request_items", "product_id", doc=D, label="Товар", new_type="bigint FK",
  description="Запрашиваемый товар.",
  be_type="BigInteger · ForeignKey('products.id', ondelete='RESTRICT')",
  be_choice_model="relationship Product", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_filter="product_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /stock/balances?warehouse_id={warehouse_id} (ОВ-5)",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("request_items", "qty", doc=D, label="Количество", new_type="numeric(14,3)",
  description="Запрошенное количество. Переносится в writeoff_items при issue().",
  be_type="Numeric(14, 3)", be_nullable="False", be_other="INV-6: CHECK (qty > 0)",
  fe_table_view=Y, fe_input_type="number", fe_required="True",
  fe_validations="required; > 0",
  comments="Резервирования нет (§8, ADR-3): наличие проверяется только в момент issue().",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)

D = "ТЗ §3 М4 writeoffs · ADR-2"
pk("writeoffs", D)
A("writeoffs", "number", doc=D + " · ADR-2a", label="Номер проводки", new_type="varchar(32)",
  description="СВОЯ, независимая серия — порча/брак заявки не имеют (ADR-2a).",
  be_type="String(32)", be_unique="True", be_nullable="False", be_db_index="True (UNIQUE)",
  be_editable="False", be_filter="number",
  fe_table_view=Y, fe_input_type="text", fe_required="False", fe_max="32", fe_disabled="True",
  comments="Второй из двух номеров. В реестре §6.4 показываются оба, поиск по любому (ОВ-6).",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("writeoffs", "date", doc=D, label="Дата проводки", new_type="date",
  description="Дата списания.",
  be_type="Date", be_nullable="False", be_db_index="True", be_filter="date__range",
  fe_table_view=Y, fe_input_type="date", fe_required="True",
  comments="При выдаче проставляется сервером = дата issue(); при порче/браке вводится админом.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("writeoffs", "warehouse_id", doc=D, label="Склад списания", new_type="bigint FK",
  description="Склад, с которого списывается товар.",
  be_type="BigInteger · ForeignKey('warehouses.id', ondelete='RESTRICT')",
  be_choice_model="relationship Warehouse", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_filter="warehouse_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /warehouses?status=active",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("writeoffs", "expense_type_id", doc=D + " · INV-4", label="Тип расхода товара", new_type="bigint FK",
  description="Выдача сотруднику / Порча / Брак.",
  be_type="BigInteger · ForeignKey('expense_types.id', ondelete='RESTRICT')",
  be_choice_model="relationship ExpenseType", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT",
  be_other="INV-4: составной FK (expense_type_id, requires_employee) -> expense_types(id, requires_employee) ON UPDATE CASCADE ON DELETE RESTRICT",
  be_filter="expense_type_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /expense-types?status=active",
  fe_validations="required; при requires_employee=true форма требует сотрудника, иначе — прячет поле",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("writeoffs", "requires_employee", doc=D + " · INV-4", label="Требует сотрудника (копия флага)", new_type="boolean",
  description="Копия expense_types.requires_employee, синхронизируемая составным FK с ON UPDATE CASCADE. Существует ТОЛЬКО чтобы выразить межтабличный INV-4 обычным CHECK.",
  be_type="Boolean", be_nullable="False", be_editable="False",
  be_db_index="True (в составе композитного FK)",
  be_other="INV-4: CHECK ((employee_id IS NOT NULL) = requires_employee)",
  fe_table_view=N, fe_input_type="checkbox", fe_required="False", fe_disabled="True",
  comments="Вторая денормализация, вне AP: обоснование — INV-4 межтабличный, обычный CHECK его не выражает. Заполняется сервером из выбранного expense_type, клиент не присылает. Подробности и альтернатива-триггер — в 02-database.md.",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("writeoffs", "employee_id", doc=D + " · INV-4", label="Сотрудник-получатель", new_type="bigint FK NULL",
  description="Получатель при «Выдаче». NULL при «Порче»/«Браке».",
  be_type="BigInteger · ForeignKey('users.id', ondelete='RESTRICT')",
  be_choice_model="relationship User", be_nullable="True", be_db_index="True (FK)",
  be_on_delete="RESTRICT",
  be_other="INV-4: CHECK ((employee_id IS NOT NULL) = requires_employee)", be_filter="employee_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False",
  fe_choice_model="GET /users?is_active=true&role__in=teacher,worker",
  fe_validations="обязателен ⟺ выбранный expense_type.requires_employee = true",
  comments="При issue() заполняется из requests.employee_id.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("writeoffs", "author_id", doc=D, label="Автор проводки", new_type="bigint FK",
  description="Кто провёл списание (завскладом). Из JWT.",
  be_type="BigInteger · ForeignKey('users.id', ondelete='RESTRICT')",
  be_choice_model="relationship User", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_editable="False", be_filter="author_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  comments="Отличается от employee_id: автор — завскладом, получатель — сотрудник.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)

D = "ТЗ §3 М4 writeoff_items"
pk("writeoff_items", D)
A("writeoff_items", "writeoff_id", doc=D, label="Проводка", new_type="bigint FK",
  description="Родительская проводка списания.",
  be_type="BigInteger · ForeignKey('writeoffs.id', ondelete='CASCADE')",
  be_choice_model="relationship Writeoff", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="CASCADE", be_filter="writeoff_id",
  fe_table_view=N, fe_input_type="number", fe_required="False", fe_disabled="True",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("writeoff_items", "product_id", doc=D, label="Товар", new_type="bigint FK",
  description="Списываемый товар.",
  be_type="BigInteger · ForeignKey('products.id', ondelete='RESTRICT')",
  be_choice_model="relationship Product", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_filter="product_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /stock/balances?warehouse_id={warehouse_id}",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("writeoff_items", "qty", doc=D, label="Количество", new_type="numeric(14,3)",
  description="Списываемое количество (положительное; знак ставит ledger).",
  be_type="Numeric(14, 3)", be_nullable="False", be_other="INV-6: CHECK (qty > 0)",
  fe_table_view=Y, fe_input_type="number", fe_required="True",
  fe_validations="required; > 0; ≤ остатка (сервер — истина)",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("writeoff_items", "reason", doc=D, label="Причина", new_type="varchar(500) NULL",
  description="Причина списания построчно (актуально для порчи/брака).",
  be_type="String(500)", be_nullable="True",
  fe_table_view=N, fe_input_type="text", fe_required="False", fe_max="500",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)

# ══════════════════════════════════════════════════════════════════════════
# М5. КАССЫ И ДЕНЬГИ
# ══════════════════════════════════════════════════════════════════════════
D = "ТЗ §3 М5 cash_desks · AP-9"
pk("cash_desks", D)
A("cash_desks", "type", doc=D, label="Касса", new_type="enum UNIQUE",
  description="teacher | worker. Ровно две строки (seed). UNIQUE гарантирует, что третьей кассы не появится.",
  be_type="SAEnum(CashDeskType, name='cash_desk_type')", be_choice_model="CashDeskType(str, Enum)",
  be_choice_enum="teacher | worker", be_unique="True", be_nullable="False",
  be_db_index="True (UNIQUE)", be_filter="type",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  fe_choice_enum="teacher | worker",
  comments="SV-6: касса выводится сервером из users.category, клиент её не выбирает.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("cash_desks", "balance", doc=D + " · INV-8 · ОВ-2", label="Баланс кассы", new_type="numeric(18,2)",
  description="Текущий остаток кассы, UZS. Обновляется в TX под FOR UPDATE (AP-9).",
  be_type="Numeric(18, 2)", be_nullable="False", be_default="0 (server_default='0')",
  be_editable="False", be_other="INV-8: CHECK (balance >= 0) — по допущению ОВ-2 (жёсткая блокировка)",
  fe_table_view=Y, fe_input_type="number", fe_required="False", fe_disabled="True",
  comments="ОВ-2 ОТКРЫТ: CHECK поставлен по принятому допущению «жёсткая блокировка». Если заказчик выберет режим предупреждения (CASH_OVERDRAFT_MODE=warn), CHECK придётся снять отдельной миграцией — единственное место, где ОВ-2 всё-таки касается схемы.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)

D = "ТЗ §3 М5 money_income"
pk("money_income", D)
A("money_income", "cash_desk_id", doc=D, label="Касса", new_type="bigint FK",
  description="Пополняемая касса.",
  be_type="BigInteger · ForeignKey('cash_desks.id', ondelete='RESTRICT')",
  be_choice_model="relationship CashDesk", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_filter="cash_desk_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /cash/desks",
  comments="Приход — только admin (§6 API), поэтому кассу здесь выбирают явно (в отличие от расхода, SV-6).",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("money_income", "amount", doc=D, label="Сумма прихода", new_type="numeric(18,2)",
  description="Сумма пополнения, UZS. Деньги — только NUMERIC, никогда float.",
  be_type="Numeric(18, 2)", be_nullable="False", be_other="CHECK (amount > 0)",
  fe_table_view=Y, fe_input_type="number", fe_required="True",
  fe_validations="required; > 0; 2 знака; UZS",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("money_income", "date", doc=D, label="Дата", new_type="date",
  description="Дата прихода.",
  be_type="Date", be_nullable="False", be_db_index="True", be_filter="date__range",
  fe_table_view=Y, fe_input_type="date", fe_required="True",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("money_income", "author_id", doc=D, label="Автор", new_type="bigint FK",
  description="Администратор, проведший приход. Из JWT.",
  be_type="BigInteger · ForeignKey('users.id', ondelete='RESTRICT')",
  be_choice_model="relationship User", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_editable="False", be_filter="author_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("money_income", "comment", doc=D, label="Комментарий", new_type="varchar(500) NULL",
  description="Основание пополнения.",
  be_type="String(500)", be_nullable="True",
  fe_table_view=N, fe_input_type="text", fe_required="False", fe_max="500",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)

D = "ТЗ §3 М5 money_expense · AP-8"
pk("money_expense", D)
A("money_expense", "cash_desk_id", doc=D + " · SV-6", label="Касса", new_type="bigint FK",
  description="Касса списания. ОПРЕДЕЛЯЕТСЯ СЕРВЕРОМ из users.category (SV-6).",
  be_type="BigInteger · ForeignKey('cash_desks.id', ondelete='RESTRICT')",
  be_choice_model="relationship CashDesk", be_nullable="False",
  be_db_index="True (composite (cash_desk_id, date DESC) — AP-8)", be_on_delete="RESTRICT",
  be_editable="False", be_filter="cash_desk_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  comments="SV-6: клиент кассу НЕ присылает (create=—). Иначе учитель спишет из кассы работников, подделав тело запроса. AP-9: FOR UPDATE по cash_desks при расходе.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("money_expense", "employee_id", doc=D + " · AP-8", label="Сотрудник", new_type="bigint FK",
  description="Кто потратил. Из JWT (сотрудник видит только свои расходы, §1.3).",
  be_type="BigInteger · ForeignKey('users.id', ondelete='RESTRICT')",
  be_choice_model="relationship User", be_nullable="False",
  be_db_index="True (composite (employee_id, date DESC) — AP-8)", be_on_delete="RESTRICT",
  be_editable="False", be_filter="employee_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("money_expense", "expense_category_id", doc=D + " · AP-8", label="Вид расхода", new_type="bigint FK",
  description="Вид расхода денег. Обязательный фильтр отчёта ДДС (AP-8).",
  be_type="BigInteger · ForeignKey('expense_categories.id', ondelete='RESTRICT')",
  be_choice_model="relationship ExpenseCategory", be_nullable="False",
  be_db_index="True (composite (expense_category_id, date DESC) — AP-8)", be_on_delete="RESTRICT",
  be_filter="expense_category_id",
  fe_table_view=Y, fe_input_type="select", fe_required="True",
  fe_choice_model="GET /expense-categories?status=active",
  comments="AP-8: «фильтр по категории обязателен» — под это отдельный composite-индекс.",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("money_expense", "amount", doc=D, label="Сумма расхода", new_type="numeric(18,2)",
  description="Сумма расхода, UZS.",
  be_type="Numeric(18, 2)", be_nullable="False", be_other="CHECK (amount > 0)",
  fe_table_view=Y, fe_input_type="number", fe_required="True",
  fe_validations="required; > 0; 2 знака; UZS; ≤ баланса кассы (сервер — истина, ОВ-2)",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)
A("money_expense", "description", doc=D, label="Описание", new_type="text",
  description="На что потрачены деньги.",
  be_type="Text", be_nullable="False", be_other="CHECK (length(trim(description)) > 0)",
  fe_table_view=N, fe_input_type="textarea", fe_required="True",
  fe_validations="required; непустая строка",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("money_expense", "receipt_url", doc=D + " · INV-7", label="Чек", new_type="varchar(500)",
  description="Ключ объекта чека в MinIO (бакет receipts). NOT NULL — чек обязателен (§7.3).",
  be_type="String(500)", be_nullable="False",
  be_other="INV-7: NOT NULL + CHECK (length(trim(receipt_url)) > 0) — иначе пустая строка обойдёт NOT NULL",
  fe_table_view=N, fe_input_type="file", fe_required="True", fe_max="500",
  fe_validations="required; whitelist jpg/png/pdf; ≤ 10 МБ; проверка по magic bytes (сервер)",
  comments="INV-7. Загрузка: POST /cash/expenses/{id}/receipt. Хранится ключ, наружу — presigned URL TTL 5 мин, бакет приватный.",
  api_get_index=N, api_get_single=Y, api_create=Y, api_update=N)
A("money_expense", "date", doc=D + " · AP-8", label="Дата", new_type="date",
  description="Дата расхода. Ключ периода в отчёте ДДС.",
  be_type="Date", be_nullable="False",
  be_db_index="True (в составе composite-индексов AP-8)", be_filter="date__range",
  fe_table_view=Y, fe_input_type="date", fe_required="True",
  api_get_index=Y, api_get_single=Y, api_create=Y, api_update=N)

# ══════════════════════════════════════════════════════════════════════════
# М7. АДМИНИСТРИРОВАНИЕ / АУДИТ
# ══════════════════════════════════════════════════════════════════════════
D = "ТЗ §3 М7 audit_log"
pk("audit_log", D)
A("audit_log", "user_id", doc=D, label="Пользователь", new_type="bigint FK",
  description="Кто выполнил действие.",
  be_type="BigInteger · ForeignKey('users.id', ondelete='RESTRICT')",
  be_choice_model="relationship User", be_nullable="False", be_db_index="True (FK)",
  be_on_delete="RESTRICT", be_editable="False", be_filter="user_id",
  fe_table_view=Y, fe_input_type="select", fe_required="False", fe_disabled="True",
  comments="Таблица append-only, пишет middleware. Чтение — только admin. API на запись нет.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("audit_log", "action", doc=D, label="Действие", new_type="varchar(50)",
  description="create | update | delete | issue | print и т.п.",
  be_type="String(50)", be_nullable="False", be_db_index="True", be_editable="False",
  be_filter="action",
  fe_table_view=Y, fe_input_type="text", fe_required="False", fe_max="50", fe_disabled="True",
  comments="varchar, не enum: множество действий расширяется с каждым новым эндпоинтом, миграция типа на каждый чих не нужна.",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("audit_log", "entity", doc=D, label="Сущность", new_type="varchar(100)",
  description="Имя таблицы/сущности, которую изменили.",
  be_type="String(100)", be_nullable="False",
  be_db_index="True (composite (entity, entity_id))", be_editable="False", be_filter="entity",
  fe_table_view=Y, fe_input_type="text", fe_required="False", fe_max="100", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("audit_log", "entity_id", doc=D, label="ID сущности", new_type="bigint NULL",
  description="ID изменённой записи. NULL для действий без объекта (например, login).",
  be_type="BigInteger", be_nullable="True",
  be_db_index="True (composite (entity, entity_id))", be_editable="False", be_filter="entity_id",
  fe_table_view=Y, fe_input_type="number", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)
A("audit_log", "payload_diff", doc=D, label="Изменения", new_type="jsonb NULL",
  description="Диф значений до/после.",
  be_type="JSONB", be_nullable="True", be_editable="False",
  fe_table_view=N, fe_input_type="textarea", fe_required="False", fe_disabled="True",
  comments="Индекс GIN не создаём: поиск по телу дифа в ТЗ не заявлен (нет access pattern).",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("audit_log", "ip", doc=D, label="IP", new_type="inet NULL",
  description="IP-адрес источника запроса.",
  be_type="INET (postgresql.INET)", be_nullable="True", be_editable="False", be_filter="ip",
  fe_table_view=N, fe_input_type="text", fe_required="False", fe_disabled="True",
  comments="Нативный inet, а не varchar: корректная валидация и сравнение подсетей.",
  api_get_index=N, api_get_single=Y, api_create=N, api_update=N)
A("audit_log", "created_at", doc=D, label="Когда", new_type="timestamptz",
  description="Момент действия.",
  be_type="DateTime(timezone=True)", be_auto="server_default=func.now()",
  be_nullable="False", be_default="now()", be_db_index="True (created_at DESC)",
  be_editable="False", be_filter="created_at__range",
  fe_table_view=Y, fe_input_type="date", fe_required="False", fe_disabled="True",
  api_get_index=Y, api_get_single=Y, api_create=N, api_update=N)


XLSX_PATH = FEATURE_DEV / "02-data-dictionary.xlsx"
CONTRACT_PATH = FEATURE_DEV / "02-contract.json"

# ОДИН вызов, ОДИН список rows -> Excel и JSON не могут разойтись.
xlsx, contract = build_all(
    rows,
    str(XLSX_PATH),
    str(CONTRACT_PATH),
    title="Складской учёт — словарь данных · PostgreSQL 16 + SQLAlchemy 2.0 + Alembic + Pydantic v2 (НЕ Django)",
)

tables = []
for r in rows:
    if r.table not in tables:
        tables.append(r.table)
print(f"rows: {len(rows)} | tables: {len(tables)}")
print(f"xlsx:     {xlsx}")
print(f"contract: {contract}")
