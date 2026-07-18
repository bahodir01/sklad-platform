# Contract → UI mapping

How the data-dictionary contract drives the frontend: type mapping, form-control
mapping, exposure rules, and the field-manifest format the validator checks.

## Type map (contract backend type → language / control)

| Contract backend type | TS type | Default control |
|---|---|---|
| `CharField`, `TextField`, `EmailField`, `SlugField` | `string` | text / textarea / email |
| `IntegerField`, `BigIntegerField`, `PositiveIntegerField` | `number` | number |
| `DecimalField`, `FloatField` | `number` | number (decimal handling) |
| `BooleanField` | `boolean` | checkbox / switch |
| `DateField`, `DateTimeField`, `TimeField` | `string` (ISO) / `Date` | date / datetime picker |
| `ForeignKey`, `OneToOneField` | id ref (`number`/`string`) | select bound to choice source |
| `ManyToManyField` | id ref array | multi-select |
| `CharField` with `choices` | union of literals | select |
| `JSONField` | `unknown` / typed shape | structured editor |
| `UUIDField` | `string` | text (read-only if pk) |
| `FileField`, `ImageField` | `string` (url) | file upload |

The `input_type` in the attribute's frontend block overrides the default when set.

## Control mapping (frontend block → form control)

- `input_type` → the control (`text` / `number` / `select` / `date` / `checkbox` /
  `textarea` / `file`).
- `required` → required validation on the field.
- `max` → maxLength for text, max for numbers.
- `disabled` → render read-only / disabled.
- `validations` → client-side validators (e.g. `email`, `> 0`, regex).
- `choice_model` / `choice_enum` → options source for a select. Prefer the
  frontend value when it differs from the backend (e.g. backend model `Customer`,
  frontend component `CustomerSelect`).
- `editable = False` → not shown in create/edit forms even if otherwise flagged.

## Exposure rules (API flags → where a field appears)

| API flag true | Field appears in |
|---|---|
| `get_index` | list / table columns |
| `get_single` | detail view |
| `create` | create form inputs and the create payload |
| `update` | edit form inputs and the update payload |

A field with none of the flags is internal and appears in no view. A field flagged
only on reads (e.g. `created_at`) is display-only — never in a create/edit form.

## Payload typing (api-integration specialist)

- **Entity/read type** — fields where `get_index` or `get_single` is true.
- **`CreateX`** — exactly the `create` fields.
- **`UpdateX`** — exactly the `update` fields (usually `Partial`).
- Never include a non-`create` field in `CreateX`, or a non-`update` field in
  `UpdateX`.

## Field-manifest format (for the UI validator)

The frontend developer emits `ui_manifest.json` listing what each view renders, so
`assets/ui_contract_validator.py` can check it against the contract without parsing
framework code:

```json
{
  "views": [
    {"name": "OrderTable",      "table": "order", "kind": "list",   "fields": ["customer", "status", "total_amount"]},
    {"name": "OrderDetail",     "table": "order", "kind": "detail", "fields": ["customer", "status", "total_amount", "created_at"]},
    {"name": "OrderCreateForm", "table": "order", "kind": "create", "fields": ["customer", "status", "total_amount"]},
    {"name": "OrderEditForm",   "table": "order", "kind": "update", "fields": ["status", "total_amount"]}
  ]
}
```

`kind` is one of `list`/`table`, `detail`, `create`, `update`/`edit`. The validator
checks that every field exists in the contract for that table and is flagged for
that view's exposure. It fails on unknown fields, unknown tables, or a field shown
in a view whose API flag is false (e.g. a read-only field placed in a create form).
