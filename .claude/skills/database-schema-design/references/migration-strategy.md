# Legacy migration strategy

When the ТЗ describes migrating an existing (legacy) database to the new Django +
PostgreSQL schema, the data dictionary's OLD block is the mapping contract, and
the migration itself is designed for **zero downtime with a rollback at every
step**.

## 1. Build the OLD → NEW mapping first

Fill the OLD block for every NEW attribute before writing any migration code.
Each row answers three questions:

- Where did this attribute come from? (`OLD ТАБЛИЦА И АТРИБУТ`)
- What was it literally called? (`OLD атрибут ОРИГ.`)
- What was its type, and does it need conversion? (`OLD ТИП ДАННЫХ` → `ТИП ДАННЫХ`)

Attributes with no legacy source are marked `🆕`. Legacy columns that are being
**dropped** get one row too, marked in `ЗАДАНИЕ` as "drop — not migrated", so the
decision is visible and reviewed rather than forgotten.

Common type conversions to flag in `other validations` / `КОММЕНТАРИИ`:

| OLD | NEW | Note |
|---|---|---|
| `float` money | `NUMERIC(12,2)` | float rounding — convert and verify totals |
| `varchar` enum | `choices` | validate every distinct old value maps to a choice |
| `int(11)` FK | `BigAutoField` FK | check range; remap orphaned references |
| `datetime` (naive) | `timestamptz` | assign the source timezone explicitly |
| `tinyint(1)` | `BooleanField` | 0/1 → False/True |

## 2. Expand → migrate → contract (zero downtime)

Never rename or retype a column in place on a live table. Use three phases:

**Expand.** Add the new tables/columns as **additive, nullable** changes. Nothing
reads them yet. This migration is instantly reversible (drop what you added).

```python
# 0001_expand.py — additive only
operations = [
    migrations.AddField(
        model_name="order",
        name="total_amount",
        field=models.DecimalField(max_digits=12, decimal_places=2, null=True),
    ),
]
```

**Migrate (backfill).** Copy and convert data from OLD to NEW in batches, so you
never lock the whole table. Make the backfill idempotent — safe to re-run.

```python
def backfill_total(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    qs = Order.objects.filter(total_amount__isnull=True)
    batch = 5000
    while qs.exists():
        ids = list(qs.values_list("id", flat=True)[:batch])
        for order in Order.objects.filter(id__in=ids):
            # convert legacy float -> Decimal safely
            order.total_amount = round_decimal(order.legacy_total)
            order.save(update_fields=["total_amount"])
```

Run it as a data migration or an out-of-band batch job for very large tables.
Verify row counts and a checksum of a sample before proceeding.

**Contract.** Once the new column is fully populated and the application reads it,
tighten constraints (`NOT NULL`, defaults) and remove the legacy column in a
later, separate deploy — after you're confident no rollback is needed.

```python
# 0003_contract.py — after backfill verified
operations = [
    migrations.AlterField(
        model_name="order",
        name="total_amount",
        field=models.DecimalField(max_digits=12, decimal_places=2, default=0),
    ),
    migrations.RemoveField(model_name="order", name="legacy_total"),
]
```

## 3. Dual-write window (when cutover can't be instant)

If old and new systems run in parallel, write to both for a window:

- Application writes go to NEW; a shim also writes OLD (or vice versa).
- A reconciliation job compares the two and reports drift.
- Cut reads over to NEW once drift is zero for a full cycle.
- Remove the dual-write shim in the contract phase.

## 4. Rollback plan (required for every phase)

- **Expand**: reverse = drop the added columns/tables. Always safe.
- **Backfill**: reverse = no schema change; the new column simply goes unused.
  Keep the OLD column until contract, so reads can fall back.
- **Contract**: this is the point of no return. Only run it after the new path has
  been verified in production. Its "rollback" is a forward-fix, so gate it behind
  explicit sign-off.

Order of safety: never contract in the same deploy as expand. Put a verification
checkpoint (counts, checksums, spot checks) between migrate and contract.

## 5. Verification checklist before contract

- Row counts match between OLD source and NEW target.
- A sampled checksum/aggregate (e.g. `SUM(total)`) matches within tolerance.
- Every distinct OLD enum value mapped to a valid NEW choice (no silent drops).
- Orphaned FKs identified and resolved.
- Application reads/writes the NEW columns in production without errors.
