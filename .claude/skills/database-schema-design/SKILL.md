---
name: database-schema-design
description: Turn a written spec (ТЗ / requirements) into a normalized relational schema plus a reviewable data dictionary. Use when designing new tables from requirements, migrating a legacy database to Django + PostgreSQL, mapping OLD schema to NEW schema, or producing an Excel data dictionary where each attribute is one row with backend constraints, frontend hints, and API CRUD flags.
---

# Database Schema Design

Turn a requirements document into a concrete, normalized schema and a data dictionary that the backend, frontend, and API layers all read as the single source of truth.

## When to Use This Skill

- Designing new tables from an analyst's ТЗ / requirements document
- Migrating a legacy database (OLD schema) to a new Django + PostgreSQL schema (NEW schema)
- Producing a per-attribute data dictionary in Excel
- Reviewing an existing schema for normalization (3NF) violations
- Planning indexes and deliberate denormalization against stated access patterns
- Designing zero-downtime migrations with rollback

## Inputs and Outputs

**What you provide (from the ТЗ):**
- The modules in scope and what each one owns
- Entities and relationships implied by the domain
- Access patterns (hot reads/writes), consistency and latency needs
- Legacy schema, if migrating (old tables, attributes, types)
- Non-functional constraints (scale, retention, PII/compliance, multi-tenancy)

**What this skill produces:**
- Engine choice with rationale (PostgreSQL by default; see the agent's engine-selection rules)
- Conceptual → logical → physical models
- SQL DDL, Django ORM models, and migration stubs
- A Mermaid ER diagram
- **An Excel data dictionary** — one row per attribute, in the exact 34-column layout below
- An index & denormalization plan tied to access patterns
- A legacy → new mapping (for migrations)

## Design Priorities (in order)

1. **Correctness through normalization (3NF).** Remove update/insert/delete anomalies first.
2. **Performance & selective denormalization.** Add indexes / denormalized columns / materialized views only against a stated read pattern, and record the justification.
3. **Flexibility for growth.** Keys, types, and module boundaries that tolerate new modules.
4. **Event-sourcing compatibility.** Append-friendly write models and clean aggregate boundaries where required.

## Workflow

1. **Parse the ТЗ into modules.** One list of modules → the entities each owns.
2. **Choose the engine** and state why.
3. **Conceptual model:** entities, attributes, relationships, cardinalities.
4. **Normalize to 3NF.** Junction tables for many-to-many; note every violation you fixed.
5. **Denormalize deliberately,** only against stated read patterns, with justification.
6. **Keys & constraints:** PK strategy, FKs with explicit `on_delete`, unique, checks, defaults, nullability.
7. **Indexes** from access patterns — cover hot queries, nothing speculative.
8. **Legacy → new mapping** (migration only): every NEW attribute references its OLD table/attribute/type, or is flagged 🆕.
9. **Emit artifacts:** DDL, Django models, migrations, Mermaid ER diagram, and the Excel data dictionary.
10. **Migration & rollback plan.**

## The Data Dictionary (primary deliverable)

The workbook has **one row per attribute** and a **three-tier header** that
reproduces the reference layout exactly (47 physical columns):

- **Row 2 (band):** `BACKEND` · `FRONTEND` · `API`
- **Row 3 (sub-band):** `Constraints` · `Filter` (under BACKEND), then a *second*
  `Constraints` · `Frontend` (under FRONTEND)
- **Row 4 (headers):** the actual columns

Column blocks, left to right:

**META** — `doc` · `ПРОВЕРЕНО` · `СТАТУС` · `НАИМЕНОВАНИЕ (LABEL)`
**NEW schema (green)** — `НАЗВАНИЕ ТАБЛИЦЫ/АТРИБУТА` (merged, 2 cells) · `🆕 ТИП ДАННЫХ` (merged, 3 cells) · `ОПИСАНИЕ`
**OLD (orange)** — `OLD ТАБЛИЦА И АТРИБУТ` · `OLD атрибут ОРИГ.` · `OLD ТИП ДАННЫХ`
**BACKEND** — `ТИП ДАННЫХ`, then a **Constraints** block (`auto fields` · `unique` · `choice — модель и параметры` · `choice / enum parametres` · `nullable / null` · `default` · `db_index` · `editable` · `on_delete` · `other validations`), then **Filter** (`filter`)
**FRONTEND** — a **second, separate Constraints block** with the same columns but frontend-side values (they can differ from backend), then **Frontend** fields (`Table view` · `input type` · `required` · `max` · `disabled` · `validations`)
**COMMENTS** — `КОММЕНТАРИИ` · `ЗАДАНИЕ`
**API** — `get_index` · `get_single` · `create` · `update`

The Constraints block appears **twice on purpose**: the BACKEND set is the Django
model constraint; the FRONTEND set is how the same attribute is constrained in the
UI. Fill the frontend set only where it differs from the backend.

Use `assets/data_dictionary_generator.py` to build the workbook so the merges, the
two Constraints blocks, and the 47-column order stay identical every time. Feed it
a list of `Attribute` rows (library) or a JSON file (CLI) — never hand-format the
column order.

## The contract — one source of truth for every agent

The Excel workbook is for humans; the **JSON contract** is for the other agents.
Build BOTH from the same rows so they can never disagree:

```python
from data_dictionary_generator import Attribute, build_all
build_all(rows, "02-data-dictionary.xlsx", "02-contract.json", title="Orders")
```

`contract.json` groups every attribute by table and carries its backend block
(type, constraints, on_delete, choices, validators), frontend block, legacy
mapping, and the API flags (`get_index` / `get_single` / `create` / `update`).
Downstream agents read this contract and reproduce names, types, and API exposure
verbatim — they do not invent or rename anything.

**Enforcement.** After the backend code is generated, run the validator:

```bash
python assets/contract_validator.py contract.json models.py [serializers.py]
```

It parses the Django models (and DRF serializers) with `ast` and fails (exit 1) on
any drift: a renamed or missing field, a wrong field type, an extra column not in
the dictionary, or a serializer using `fields = "__all__"` instead of honoring the
per-field API flags. A clean exit (0) means the code matches the table exactly.

Full column semantics and fill-in rules are in `references/data-dictionary-spec.md`.
Modeling method is in `references/details.md`; legacy migration in
`references/migration-strategy.md`.

## Best Practices

- Surrogate PKs by default; justify natural keys.
- Every FK declares an explicit `on_delete`.
- Narrowest correct type: money → `NUMERIC`, timestamps → `timestamptz`, small closed sets → Django `choices`, large/user-managed sets → lookup tables.
- `created_at`/`updated_at` via `auto_now_add`/`auto_now`, marked non-editable.
- Index FKs and hot `WHERE`/`ORDER BY` columns — nothing speculative.
- Enforce uniqueness in the database, not only the app.
- Migrations: additive first → backfill → switch; always provide rollback.
- Keep module boundaries clean for a future database-per-service split.
