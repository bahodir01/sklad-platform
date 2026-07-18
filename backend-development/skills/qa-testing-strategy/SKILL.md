---
name: qa-testing-strategy
description: Plan and build a feature's QA — a prioritized test plan across every testing type, and test cases generated from the database-architect's data-dictionary contract. Use when planning test coverage, designing functional/UAT/smoke/regression cases, scoping non-functional testing (performance/security/usability/compatibility), or automating tests with Playwright and pytest. Covers all levels (unit/integration/system/UAT) and access styles (black/white/grey box).
---

# QA Testing Strategy

Plan and execute a feature's quality assurance so coverage is deliberate, not
accidental. The data-dictionary contract is the backbone: field rules become test
cases automatically, the same way the backend and frontend are generated from it.

## When to Use This Skill

- Building a prioritized, risk-based test plan from the ТЗ and the contract
- Designing functional, acceptance (UAT), smoke, and regression cases
- Scoping non-functional testing: performance, security, usability, compatibility
- Choosing levels (unit/integration/system/UAT) and access styles (black/white/grey)
- Automating tests with Playwright (E2E/UI) and pytest (unit/integration/API)
- Generating field-level cases automatically from the contract

## The testing taxonomy (what "complete coverage" means)

**1. By object (what we verify)**
- Functional — behavior matches the ТЗ and contract
- Non-functional — performance, security, usability, compatibility

**2. By code access (how we test)**
- Black box — via UI/API, no code knowledge
- White box — with code knowledge (branches, internals)
- Grey box — partial knowledge (known schema + black-box UI)

**3. By level / stage (when)**
- Unit → Integration → System → Acceptance (UAT)

**4. By automation**
- Automated — Playwright + pytest, wired into CI

**5. Specific critical checks**
- Smoke (critical paths after a build), Regression (nothing broke)

A plan is complete when every ТЗ acceptance criterion and every contract field/rule
maps to at least one case, at the right level and access style, with a priority.

## The contract drives test cases

For every attribute in `contract.json`, derive cases from its rules:

- **required / nullable** → missing → fail; present → pass
- **unique** → duplicate → reject
- **choice / enum** → each valid value passes; invalid rejected
- **type** → valid and invalid formats (Decimal, Date, Boolean, FK, …)
- **max / boundary** → at / below / above the limit (boundary-value analysis)
- **default** → omit → declared default applied
- **API flags** → list/detail carry exactly get_index/get_single fields;
  create/update accept exactly the flagged fields

Use `assets/testcase_generator.py` to emit these cases from the contract as a
structured checklist the functional-tester and automation-engineer work from —
so field coverage is complete by construction.

## Two sources of test cases: fields AND flows

Field-level cases from the contract are only half the picture. They prove each
input behaves, but not that the product does what the analyst intended along a real
journey. Complete coverage needs both:

- **Field-level cases** (functional-tester, from the contract) — required, unique,
  enum, boundary, type, per attribute.
- **Scenario-level cases** (test-case-designer, from the ТЗ and user flows):
  - *Requirements-based*: every acceptance criterion / business rule in the ТЗ
    becomes ≥ 1 case (positive, negative, per role).
  - *User-flow*: each journey's happy path, alternative paths, and error/edge
    paths, plus entity state transitions (e.g. order new → paid → shipped).

## Traceability (prove every requirement is tested)

Maintain a matrix linking `requirement (ТЗ id) → test case(s) → status →
defect(s)`. Build it with `assets/traceability_matrix.py` from two files:

- `requirements.json` — one entry per ТЗ acceptance criterion/rule (`id`, `text`,
  `priority`).
- `cases.json` — cases with a `covers: [REQ-ids]` field (and optional `status`,
  `defects`).

```bash
python assets/traceability_matrix.py requirements.json cases.json --markdown matrix.md
```

It flags **uncovered requirements** (a ТЗ requirement with no test — a coverage
hole) and **orphan cases** (a test with no requirement), and exits non-zero if any
requirement is uncovered — so the pipeline can gate on "every requirement has a
test".

## Test design techniques

Beyond the contract, apply classic techniques: equivalence partitioning,
boundary-value analysis, decision tables, state-transition testing (for lifecycle
fields like an order status), pairwise for combinatorial inputs, and risk-based
prioritization (P0 critical paths → P1 core → P2 edges).

## Default automation stack

- **Playwright** — E2E/UI, Page Object Model, stable role/label/`data-testid`
  locators, fixtures for isolation, trace on failure.
- **pytest** — unit/integration/API, fixtures, parametrization for data-driven
  cases from the contract.
- Match an existing project's frameworks; don't add a second E2E framework.
- Smoke runs on every PR; the full suite on merge/nightly.

Templates live in `assets/` (`playwright_e2e_template.spec.ts`,
`pytest_api_template.py`). Details on levels, access styles, and non-functional
scoping are in `references/test-taxonomy.md`; the contract→case mapping and
generator format are in `references/contract-to-cases.md`.

## Workflow

1. **Plan** (qa-lead) — risk assessment + a test matrix mapping features/fields to
   type, level, access style, priority, owner.
2. **Design functional** (functional-tester) — generate contract cases, write UAT
   from the ТЗ, tag smoke and regression.
3. **Scope non-functional** (non-functional-tester) — performance thresholds,
   security checks, usability heuristics, compatibility matrix.
4. **Automate** (automation-engineer) — Playwright + pytest, smoke first, then
   regression, parametrized from the contract; wire CI.
5. **Consolidate** (qa-lead) — results, defects by severity, coverage, go/no-go.

## Best Practices

- Generate field coverage from the contract; don't hand-list.
- Emphasize negative testing (missing/invalid/duplicate/unauthorized), not just
  happy paths.
- Keep levels distinct: unit for logic, integration for seams, system for flows,
  UAT for acceptance.
- Every fixed defect gets a regression case.
- Make smoke fast enough to gate every PR; keep automated tests isolated and
  idempotent; fix flakes at the root.
