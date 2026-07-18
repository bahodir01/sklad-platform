# Data Dictionary — column specification

One row per attribute. The header is a **three-tier** structure that reproduces
the reference layout exactly:

- **Row 1** — title banner.
- **Row 2 (band)** — top groups: `BACKEND`, `FRONTEND`, `API` (META / NEW / OLD /
  COMMENTS columns have no band label).
- **Row 3 (sub-band)** — `Constraints`, `Filter` (under BACKEND) and a second
  `Constraints`, `Frontend` (under FRONTEND).
- **Row 4 (headers)** — the actual column names.

Data starts at row 5. The generator (`assets/data_dictionary_generator.py`) fixes
the order and the merges; this document defines what each column means.

**47 physical columns** in total, because two columns in the NEW block are merged
wide and the Constraints block appears **twice** (once for backend, once for
frontend).

## META (no band)

| Column | Meaning | Values |
|---|---|---|
| `doc` | source doc / ticket | free text |
| `ПРОВЕРЕНО` | reviewer initials | free text |
| `СТАТУС` | design state | `draft` · `review` · `done` |
| `НАИМЕНОВАНИЕ (LABEL)` | human label | free text |

## NEW schema (green, no band — some columns merged wide)

| Column | Merge | Meaning |
|---|---|---|
| `НАЗВАНИЕ ТАБЛИЦЫ/АТРИБУТА` | spans 2 cells | `table.attribute` (generated from `table` + `attribute`) |
| `🆕 ТИП ДАННЫХ` | spans 3 cells | conceptual/new type |
| `ОПИСАНИЕ` | 1 | plain-language description |

## OLD legacy mapping (orange, no band)

| Column | Meaning |
|---|---|
| `OLD ТАБЛИЦА И АТРИБУТ` | legacy `table.attribute`, or `🆕` if new |
| `OLD атрибут ОРИГ.` | original legacy name |
| `OLD ТИП ДАННЫХ` | legacy type (`varchar(20)`, `int(11)`, `float`, ...) |

## BACKEND band

`ТИП ДАННЫХ`, then a **Constraints** sub-band, then a **Filter** sub-band.

| Column | Field | Maps to Django |
|---|---|---|
| `ТИП ДАННЫХ` | `be_type` | field class (falls back to 🆕 type) |
| `auto fields (auto_now, auto_now_add, auto + comment)` | `be_auto` | `auto_now` / `auto_now_add` |
| `unique` | `be_unique` | `unique=` |
| `choice, наименование модели и параметры` | `be_choice_model` | related model / choices class |
| `choice / enum parametres` | `be_choice_enum` | the enum values |
| `nullable / null` | `be_nullable` | `null=` |
| `default (value)` | `be_default` | `default=` |
| `db_index` | `be_db_index` | `db_index=` |
| `editable` | `be_editable` | `editable=` |
| `on_delete` | `be_on_delete` | FK `on_delete=` (mandatory on FKs) |
| `other validations` | `be_other` | validators / constraints |
| `filter` (Filter sub-band) | `be_filter` | exposed queryset filter field |

## FRONTEND band

A **second, separate Constraints block** (same column names, but frontend-side
values — they can differ from the backend), then a **Frontend** sub-band.

Second Constraints block: `fe_unique`, `fe_choice_model`, `fe_choice_enum`,
`fe_nullable`, `fe_default`, `fe_db_index`, `fe_editable`, `fe_auto`,
`fe_on_delete`, `fe_other`.

Frontend fields:

| Column | Field | Meaning |
|---|---|---|
| `Table view` | `fe_table_view` | shown in list/grid (`✓`/`—`) |
| `input type` | `fe_input_type` | `text` · `number` · `select` · `date` · `checkbox` |
| `required` | `fe_required` | `True`/`False` |
| `max` | `fe_max` | max length/value |
| `disabled` | `fe_disabled` | read-only in the form |
| `validations` | `fe_validations` | client-side rules |

**Why the Constraints block appears twice:** the BACKEND set describes the Django
model constraint; the FRONTEND set describes how the same attribute is constrained
in the UI. They legitimately differ — e.g. a field that is `editable=True` in the
model but `disabled` on a particular form, or a choices source that is a model on
the backend and a dedicated dropdown component on the frontend.

## COMMENTS (no band)

| Column | Field | Meaning |
|---|---|---|
| `КОММЕНТАРИИ` | `comments` | review notes |
| `ЗАДАНИЕ` | `task` | outstanding task |

## API band (CRUD flags)

| Column | Field | Appears in |
|---|---|---|
| `get_index` | `api_get_index` | list endpoint payload |
| `get_single` | `api_get_single` | detail endpoint payload |
| `create` | `api_create` | create request body |
| `update` | `api_update` | update request body |

Mark with `✓` / `—`. Auto/PK/timestamp fields are typically `✓` on reads and
`—` on create/update.

## Filling rules

- Group attributes of one table together; keep attribute order stable so reviews
  diff cleanly.
- Leave a cell blank rather than "n/a".
- Fill the FRONTEND Constraints block only where it differs from BACKEND;
  otherwise leave blank (blank = "same as backend / not applicable").
- The generator adds a **Legend** sheet and an AutoFilter on the header row.
