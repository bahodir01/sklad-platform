# Contract → test cases

How the QA agents derive test cases automatically from the data-dictionary
contract (`02-contract.json`), and the format the generator emits.

## Why generate from the contract

The contract already declares every field's rules — required, unique, choices,
type, default, and API exposure. Instead of hand-writing cases (and missing some),
the QA agents generate them from those rules, so field-level coverage is complete
by construction and stays in sync when the dictionary changes. This mirrors how the
backend and frontend are generated from the same contract.

Use `assets/testcase_generator.py`:

```bash
python assets/testcase_generator.py contract.json cases.json --markdown cases.md
```

## Rule → case mapping

For each attribute, the generator emits:

| Contract rule | Case(s) generated | Technique |
|---|---|---|
| `required` / `nullable=false` (writable) | submit without it → must fail | negative/required |
| `unique=true` | duplicate value → must be rejected | negative/unique |
| `choice_enum` | each valid value passes; an invalid one is rejected | equivalence |
| `type` (Email/Decimal/Date/Bool/UUID/Int) | invalid format → rejected | negative/type |
| `max` (frontend) | at / below / above the limit | boundary-value |
| `default` (writable) | omit → default applied | positive/default |
| `api.get_index` | list endpoint exposes the field | contract/exposure |
| `api.create` (per table) | create payload accepts exactly the create fields | contract/payload |

State-transition fields (e.g. an order `status` with choices) also warrant
transition cases (new → paid → shipped; illegal transitions rejected) — the
functional-tester adds these on top of the generated set.

## Priority assignment

The generator assigns a rough risk-based priority:
- **P0** — writable fields with `unique` or non-nullable constraints, and the
  create-payload-shape case.
- **P1** — other writable/exposed fields.
- **P2** — defaults and non-critical cases.

The qa-lead can re-prioritize based on the ТЗ's risk areas.

## Output format

Each case:

```json
{
  "id": "order.email::required",
  "table": "order",
  "attribute": "email",
  "type": "functional",
  "technique": "negative/required",
  "priority": "P0",
  "title": "Reject when required field 'email' is missing",
  "steps": ["Submit a create request for 'order' omitting 'email'."],
  "expected": "Request is rejected with a validation error for that field."
}
```

## How each agent uses it

- **functional-tester** — takes the generated cases as its base checklist, adds
  UAT scenarios from the ТЗ and state-transition cases, tags the smoke and
  regression subsets.
- **automation-engineer** — parametrizes Playwright/pytest from the same cases
  (one parametrized test per rule family), so adding a field to the dictionary
  automatically extends the automated suite.
- **qa-lead** — folds the generated cases into the test matrix with level and
  access-style assignments.

## Templates

`assets/pytest_api_template.py` — parametrized API tests (required/unique/choice/
type) reading a cases file. `assets/playwright_e2e_template.spec.ts` — a Page
Object Model E2E skeleton with a form-validation example. Both are starting points
the automation-engineer adapts to the project.
