# Test taxonomy

The full matrix the QA agents cover, with practical guidance on when each applies.

## 1. By object — what we verify

### Functional
Behavior matches the ТЗ and the contract. Owned by functional-tester. Generated
largely from the contract (see `contract-to-cases.md`) plus UAT scenarios from the
ТЗ.

### Non-functional
How well it works. Owned by non-functional-tester.
- **Performance** — load, stress, spike, soak. Threshold-based pass/fail (p95
  latency, error rate, throughput). Default tools: k6 / Locust.
- **Security** — OWASP-relevant checks, authn/authz per endpoint, input
  validation/injection targeted by contract field types. Deep audit →
  security-auditor.
- **Usability** — heuristic evaluation of primary flows, error/empty-state
  clarity, form friction.
- **Compatibility** — target browsers/OS/devices/viewports from the ТЗ, as a
  matrix.

## 2. By code access — how we test

- **Black box** — through UI/API without code knowledge; assert observable
  outcomes. Best for UAT and most functional/E2E.
- **White box** — with code knowledge; cover specific branches, error paths, and
  internal logic. Best for unit tests and targeted coverage.
- **Grey box** — partial knowledge; use the schema/contract to design sharper
  black-box cases (e.g. test a unique constraint you know exists). Most
  contract-driven cases are grey box.

The qa-lead assigns an access style per area; a single feature usually mixes all
three (white-box units, grey-box API cases, black-box E2E/UAT).

## 3. By level / stage — when

- **Unit** — a single function/method in isolation; fast, white box; pytest.
- **Integration** — components/services together (e.g. view + serializer + DB, or
  service + queue); catches seam defects.
- **System** — the whole feature end to end through its real interfaces; Playwright
  E2E.
- **Acceptance (UAT)** — against the ТЗ's acceptance criteria, phrased as user
  scenarios; black box; the go/no-go gate.

Keep levels distinct — don't test business logic only through slow E2E, and don't
try to prove a whole flow with unit tests. Each level catches a different class of
defect.

## 4. By automation

Automated suites (automation-engineer): Playwright for E2E/UI, pytest for
unit/integration/API, wired into CI. Smoke runs on every PR; the full suite runs on
merge/nightly. Manual testing still applies for exploratory and usability work.

## 5. Specific critical checks

- **Smoke** — a small, fast set of critical-path checks that must pass after any
  build; gates the pipeline. If smoke is red, stop.
- **Regression** — a growing set guarding previously-working behavior and every
  fixed defect. Every closed defect adds a regression case so it can't return.

## Prioritization (applied across all of the above)

- **P0** — critical paths: auth, payments, data integrity, primary ТЗ flows,
  unique/required constraints on writable fields.
- **P1** — core functionality and common variations.
- **P2** — edge cases, rare inputs, non-critical UX.

Cover P0 to green before spending P1/P2 effort. The qa-lead's test matrix records
type × level × access × priority × owner for every case so nothing falls through.
