---
description: "Orchestrate end-to-end feature development from requirements to deployment"
argument-hint: "<feature description> [--methodology tdd|bdd|ddd] [--complexity simple|medium|complex]"
---

# Feature Development Orchestrator

## CRITICAL BEHAVIORAL RULES

You MUST follow these rules exactly. Violating any of them is a failure.

1. **Execute steps in order.** Do NOT skip ahead, reorder, or merge steps.
2. **Write output files.** Each step MUST produce its output file in `.feature-dev/` before the next step begins. Read from prior step files — do NOT rely on context window memory.
3. **Stop at checkpoints.** When you reach a `PHASE CHECKPOINT`, you MUST stop and wait for explicit user approval before continuing. Use the AskUserQuestion tool with clear options.
4. **Halt on failure.** If any step fails (agent error, test failure, missing dependency), STOP immediately. Present the error and ask the user how to proceed. Do NOT silently continue.
5. **Use only local agents.** All `subagent_type` references use agents bundled with this plugin or `general-purpose`. No cross-plugin dependencies.
6. **Never enter plan mode autonomously.** Do NOT use EnterPlanMode. This command IS the plan — execute it.

## Pre-flight Checks

Before starting, perform these checks:

### 1. Check for existing session

Check if `.feature-dev/state.json` exists:

- If it exists and `status` is `"in_progress"`: Read it, display the current step, and ask the user:

  ```
  Found an in-progress feature development session:
  Feature: [name from state]
  Current step: [step from state]

  1. Resume from where we left off
  2. Start fresh (archives existing session)
  ```

- If it exists and `status` is `"complete"`: Ask whether to archive and start fresh.

### 2. Initialize state

Create `.feature-dev/` directory and `state.json`:

```json
{
  "feature": "$ARGUMENTS",
  "status": "in_progress",
  "methodology": "traditional",
  "complexity": "medium",
  "current_step": 1,
  "current_phase": 1,
  "completed_steps": [],
  "files_created": [],
  "started_at": "ISO_TIMESTAMP",
  "last_updated": "ISO_TIMESTAMP"
}
```

Parse `$ARGUMENTS` for `--methodology` and `--complexity` flags. Use defaults if not specified.

### 3. Parse feature description

Extract the feature description from `$ARGUMENTS` (everything before the flags). This is referenced as `$FEATURE` in prompts below.

---

## Phase 1: Discovery (Steps 1–2) — Interactive

### Step 1: Requirements Gathering (ТЗ)

This step produces the ТЗ — the detailed requirements document the whole pipeline
traces back to. Elicit the details interactively, then have the requirements
analyst write the spec so it is precise enough for the database architect to
design the schema without guessing.

**1a. Elicit.** Ask the user questions ONE at a time using the AskUserQuestion
tool (do NOT ask them all at once), prioritizing what the schema will depend on:

1. **Problem & users**: "What problem does this feature solve? Who is the user and what's their pain point?"
2. **Modules in scope**: "What functional modules does this cover? (e.g. auth, catalog, orders, billing)"
3. **Entities & relationships**: "What are the main things the system stores in each module, and how do they relate? (e.g. an order has many order-items; a customer places many orders)"
4. **Access patterns**: "What are the important reads and writes? What gets listed, filtered, or sorted, and what must be fast?"
5. **Data rules**: "Any uniqueness, required fields, fixed value sets (enums), or domain rules?"
6. **Legacy system**: "Does this replace or migrate an existing database? If so, what are its current tables/attributes/types?"
7. **Constraints & scope**: "Any scale/latency/consistency/compliance needs, a mandated database engine or stack — and what is explicitly OUT of scope?"

**1b. Write the ТЗ.** Pass the answers to the requirements analyst to produce the
structured spec:

```
Task:
  subagent_type: "backend-development-requirements-analyst"
  description: "Write the ТЗ for $FEATURE"
  prompt: |
    Write a detailed requirements document (ТЗ) for this feature from the
    stakeholder answers below. It must be precise enough for a database architect
    to design the schema without guessing.

    ## Feature
    $FEATURE

    ## Stakeholder answers
    [Insert the user's answers from 1a, labeled by question]

    ## Produce these sections
    - Problem statement and target users
    - Modules (each with a one-line responsibility)
    - Entities & relationships (per module: entities, their attributes with rough
      types, and relationships with cardinalities)
    - Access patterns (hot reads/writes and what they filter/sort on)
    - Data rules (uniqueness, required, enums, invariants)
    - Legacy mapping notes (if migrating: old tables/attributes/types)
    - Non-functional requirements (scale, latency, consistency, compliance,
      mandated engine/stack)
    - Scope (in / out)
    - Open questions & assumptions (state anything unresolved explicitly)

    Also record the chosen Methodology (tdd|bdd|ddd|traditional) and Complexity
    (simple|medium|complex) at the end.
```

Save the analyst's output to `.feature-dev/01-requirements.md`. If it lists open
questions that block schema design, resolve them with the user before continuing.

Update `state.json`: set `current_step` to 2, add `"01-requirements.md"` to `files_created`, add step 1 to `completed_steps`.

### Step 2: Database Design

The requirements document (ТЗ) from Step 1 is the analyst's hand-off. Pass it to
the database architect FIRST — the data layer informs service and API design, so
this runs before the backend architecture step.

Read `.feature-dev/01-requirements.md` to load the ТЗ.

Use the Task tool to launch the database architect:

```
Task:
  subagent_type: "backend-development-database-architect"
  description: "Design database schema for $FEATURE"
  prompt: |
    Design the database schema for this feature from the requirements (ТЗ) below.

    ## Requirements (ТЗ)
    [Insert full contents of .feature-dev/01-requirements.md]

    ## Instructions
    1. Parse the ТЗ into modules and list the entities each module owns.
    2. Choose the database engine and state the rationale (PostgreSQL by default;
       pick another only if the ТЗ requires it).
    3. Normalize to 3NF; note any violations you resolved. Denormalize only
       against a stated access pattern, and record the justification.
    4. Define keys, constraints (explicit on_delete on every FK), and indexes
       tied to the access patterns in the ТЗ.
    5. If the ТЗ describes a legacy database, map every NEW attribute to its OLD
       table/attribute/type (or mark it 🆕), following references/migration-strategy.md.

    ## Deliverables
    - Engine choice with rationale
    - Module → entity breakdown
    - Mermaid ER diagram
    - SQL DDL and Django ORM models
    - Migration stubs with rollback
    - The Excel data dictionary AND its JSON contract — build BOTH from the SAME
      attribute rows using the database-schema-design skill's
      assets/data_dictionary_generator.py `build_all(rows, xlsx_path, contract_path)`
      so the human table and the machine contract are guaranteed identical.
      Save the workbook to .feature-dev/02-data-dictionary.xlsx and the contract
      to .feature-dev/02-contract.json
    - Index & denormalization plan tied to access patterns

    The JSON contract is the SINGLE SOURCE OF TRUTH for every downstream agent:
    table names, attribute names, backend types, and the API flags
    (get_index / get_single / create / update) come from it verbatim. Do not let
    later steps invent or rename anything the contract defines.

    Write the design as a markdown document, and produce BOTH the .xlsx and .json.
```

Save the agent's markdown output to `.feature-dev/02-database.md`, and ensure the
workbook is at `.feature-dev/02-data-dictionary.xlsx` and the contract is at
`.feature-dev/02-contract.json`.

Update `state.json`: set `current_step` to 3, add `"02-database.md"`,
`"02-data-dictionary.xlsx"`, and `"02-contract.json"` to `files_created`, add step
2 to `completed_steps`.

### Step 3: Architecture & Security Design

Read `.feature-dev/01-requirements.md` and `.feature-dev/02-database.md` to load
requirements and the schema the services will build on.

Use the Task tool to launch the architecture agent:

```
Task:
  subagent_type: "backend-development-backend-architect"
  description: "Design architecture for $FEATURE"
  prompt: |
    Design the technical architecture for this feature, building on the approved
    database schema.

    ## Requirements
    [Insert full contents of .feature-dev/01-requirements.md]

    ## Database Design
    [Insert full contents of .feature-dev/02-database.md]

    ## Deliverables
    1. **Service/component design**: What components are needed, their responsibilities, and boundaries
    2. **API design**: Endpoints, request/response schemas, error handling — align field exposure with the data dictionary's API (get_index / get_single / create / update) flags
    3. **Data access layer**: Repositories/DAOs over the schema from Step 2 (do NOT redesign tables — consume them)
    4. **Security considerations**: Auth requirements, input validation, data protection, OWASP concerns
    5. **Integration points**: How this connects to existing services/systems
    6. **Risk assessment**: Technical risks and mitigation strategies

    Write your complete architecture design as a single markdown document.
```

Save the agent's output to `.feature-dev/03-architecture.md`.

Update `state.json`: set `current_step` to "checkpoint-1", add step 3 to `completed_steps`.

---

## PHASE CHECKPOINT 1 — User Approval Required

You MUST stop here and present the database design and architecture for review.

Display a summary of the database design from `.feature-dev/02-database.md`
(engine choice, modules → entities, key tables, and the data dictionary at
`.feature-dev/02-data-dictionary.xlsx`) and of the architecture from
`.feature-dev/03-architecture.md` (key components, API endpoints), then ask:

```
Database and architecture design is complete. Please review:
- .feature-dev/02-database.md  +  .feature-dev/02-data-dictionary.xlsx
- .feature-dev/03-architecture.md

1. Approve — proceed to implementation
2. Request changes — tell me what to adjust
3. Pause — save progress and stop here
```

Do NOT proceed to Phase 2 until the user selects option 1. If they select option 2, revise the architecture and re-checkpoint. If option 3, update `state.json` status and stop.

---

## Phase 2: Implementation (Steps 3–5)

### Step 4: Backend Implementation

Read `.feature-dev/01-requirements.md`, `.feature-dev/03-architecture.md`, and the
data-dictionary contract `.feature-dev/02-contract.json`.

Use the Task tool to launch the backend architect for implementation:

```
Task:
  subagent_type: "backend-development-backend-architect"
  description: "Implement backend for $FEATURE"
  prompt: |
    Implement the backend for this feature based on the approved architecture,
    strictly conforming to the data-dictionary contract.

    ## Requirements
    [Insert contents of .feature-dev/01-requirements.md]

    ## Architecture
    [Insert contents of .feature-dev/03-architecture.md]

    ## Data dictionary contract (SINGLE SOURCE OF TRUTH)
    [Insert full contents of .feature-dev/02-contract.json]

    ## Binding rules — the contract governs the code
    - Table names, attribute names, and backend field types MUST match the
      contract EXACTLY. Do not rename, add, drop, or retype anything the contract
      defines. If the contract seems wrong, STOP and report it — do not "fix" it
      in code.
    - Django model fields come straight from each attribute's backend block:
      type, unique, nullable/null, default, db_index, editable, on_delete,
      choices (choice_model / choice_enum), and validators (other_validations).
    - DRF serializers MUST expose fields per the api flags: a field appears in the
      create payload only if api.create is true, in the update payload only if
      api.update is true, and in list/detail reads per get_index / get_single.
      Do NOT use fields = "__all__" — list fields explicitly to honor the flags.
    - Legacy attributes (legacy.is_new = false) keep their OLD→NEW mapping; follow
      the migration-strategy reference for backfill and rollback.

    ## Instructions
    1. Generate Django models, migrations, serializers, and views/viewsets from
       the contract.
    2. Add business logic, input validation, and error handling.
    3. Follow the project's existing code patterns and conventions.
    4. If methodology is TDD: write failing tests first, then implement.

    Write all code files. Report the paths of the generated models.py and
    serializers.py so they can be validated against the contract.
```

Save a summary to `.feature-dev/04-backend.md` (files created/modified, key
decisions, the models.py and serializers.py paths).

**Mandatory contract check.** After the agent finishes, run the validator from the
database-schema-design skill against the generated code:

```
python skills/database-schema-design/assets/contract_validator.py \
    .feature-dev/02-contract.json <models.py path> [<serializers.py path>]
```

If it exits non-zero, the backend code has drifted from the data dictionary. STOP,
show the reported mismatches, and either fix the code to match the contract or, if
the contract itself is wrong, return to Step 2 to revise the dictionary and
regenerate the contract. Do NOT proceed while the validator reports mismatches.

Update `state.json`: set `current_step` to 5, add step 4 to `completed_steps`.

### Step 5: Frontend Implementation

The frontend is built by dedicated agents from the SAME contract the backend used,
mirroring the backend flow: architect designs the structure, the api-integration
specialist generates the typed client, the developer writes the components, and the
UI is validated against the contract.

**If the feature has no UI (pure backend/API), skip this step** — write a brief note
in `05-frontend.md` explaining why, and continue.

Read `.feature-dev/01-requirements.md`, `.feature-dev/03-architecture.md`,
`.feature-dev/04-backend.md`, and the contract `.feature-dev/02-contract.json`.

**5.0 — Visual design (optional but recommended for user-facing features).** Use the
`design-orchestrator` skill to generate the visual mockup and design tokens from the
ТЗ and the client's style choice, before component structure is decided. The
orchestrator routes to one branch by project type: WEB (landing/corporate/
ecommerce/saas) → web-designer, APP (crm/dashboard/admin/webapp/mobile) →
interface-designer, or 3D (immersive/style_preset=3d) → web3d-designer. It loads
only the active branch to save context.

Provide it two inputs (see the skill's SKILL.md for the exact schema):
- `brief` — derived from the ТЗ (`01-requirements.md`): project_type, goal,
  audience, pages/sections, content, conversion actions, data entities.
- `client_choice` — the client's `style_preset` plus `overrides` (palette, fonts,
  must-have, avoid) and optional `stack`.

If the client's style choice isn't captured yet, elicit it (preset + overrides)
before generating. Save the design tokens to `.feature-dev/05-design-tokens.json`
and the mockup artifact to `.feature-dev/05-design-mockup.html` (or `.jsx`). These
feed the UI architecture and implementation below so the built components match the
approved visual design.

**5a. UI architecture.** Launch the frontend architect (pass the design tokens so
the structure honors the visual design):

```
Task:
  subagent_type: "backend-development-frontend-architect"
  description: "Design UI architecture for $FEATURE"
  prompt: |
    Design the frontend architecture from the ТЗ, the data-dictionary contract, and
    the approved visual design.

    ## Requirements (ТЗ)
    [Insert contents of .feature-dev/01-requirements.md]
    ## Backend / endpoints
    [Insert contents of .feature-dev/04-backend.md]
    ## Data dictionary contract (SINGLE SOURCE OF TRUTH)
    [Insert full contents of .feature-dev/02-contract.json]
    ## Design tokens & mockup (from design-orchestrator, if produced)
    [Insert contents of .feature-dev/05-design-tokens.json and reference 05-design-mockup.html]

    Choose the framework and language from the ТЗ (state the rationale). Produce:
    the component tree, routing map, state/cache strategy, and a data-binding plan
    mapping each screen/form to contract attributes (list → get_index, detail →
    get_single, create/edit → create/update), plus the API-consumption points.
    Use the design tokens for spacing/color/typography. Follow the
    frontend-component-design skill for accessibility.
```

Save to `.feature-dev/05a-frontend-architecture.md`.

**5b. Typed API layer + components (in parallel).** Launch both agents in one
response, each receiving the contract and the architecture from 5a:

```
Task:
  subagent_type: "backend-development-api-integration-specialist"
  description: "Generate typed API layer for $FEATURE"
  prompt: |
    Generate the typed API-integration layer from the contract and endpoints.
    ## Contract
    [Insert full contents of .feature-dev/02-contract.json]
    ## UI architecture
    [Insert contents of .feature-dev/05a-frontend-architecture.md]
    ## Backend endpoints
    [Insert contents of .feature-dev/04-backend.md]

    Generate entity/read types, CreateX from the create fields, UpdateX from the
    update fields, client functions per endpoint, and hooks/services with cache
    invalidation on writes. Never include a non-create field in CreateX or a
    non-update field in UpdateX. Report the generated types and clients.
```

```
Task:
  subagent_type: "backend-development-frontend-developer"
  description: "Implement frontend components for $FEATURE"
  prompt: |
    Implement the components from the architecture and the contract.
    ## UI architecture
    [Insert contents of .feature-dev/05a-frontend-architecture.md]
    ## Contract (SINGLE SOURCE OF TRUTH)
    [Insert full contents of .feature-dev/02-contract.json]

    Binding rules (the contract governs the UI):
    - Field names in forms, tables, and payloads match contract attribute names EXACTLY.
    - Build controls from each attribute's frontend block (input_type, required,
      max, disabled, validations, choice source). Honor the frontend value when it
      differs from the backend.
    - Tables render get_index fields; detail views render get_single; create forms
      include exactly the create fields; edit forms exactly the update fields.
    - Types line up with the contract's backend types.
    Use the typed API layer from the integration specialist. Build loading/empty/
    error states and accessibility in from the start.

    IMPORTANT: also emit a field manifest `.feature-dev/05-ui-manifest.json` listing
    every view: {name, table, kind (list|detail|create|update), fields:[...]}. This
    is validated against the contract.
```

Save a summary to `.feature-dev/05-frontend.md` (files created, and which contract
attributes each form/table binds to), and ensure `.feature-dev/05-ui-manifest.json`
exists.

**Mandatory UI contract check.** Run the frontend validator:

```
python skills/frontend-component-design/assets/ui_contract_validator.py \
    .feature-dev/02-contract.json .feature-dev/05-ui-manifest.json
```

If it exits non-zero, the UI has drifted from the data dictionary (a field not in
the contract, a read-only field in a create form, etc.). STOP, show the mismatches,
and fix the UI — or, if the dictionary is wrong, return to Step 2, revise it, and
regenerate the contract. Do NOT proceed while the validator reports mismatches.

Update `state.json`: set `current_step` to 6, add step 5 to `completed_steps`.

### Step 6: Testing & Validation

Read `.feature-dev/04-backend.md`, `.feature-dev/05-frontend.md`, and the contract
`.feature-dev/02-contract.json`.

**6.0 — QA plan & generated cases.** First, generate field-level test cases from
the contract, then have the QA lead build the test plan:

```
python skills/qa-testing-strategy/assets/testcase_generator.py \
    .feature-dev/02-contract.json .feature-dev/06-qa-cases.json \
    --markdown .feature-dev/06-qa-cases.md
```

```
Task:
  subagent_type: "backend-development-qa-lead"
  description: "Plan QA for $FEATURE"
  prompt: |
    Build the test plan for this feature.
    ## ТЗ
    [Insert contents of .feature-dev/01-requirements.md]
    ## Contract
    [Insert full contents of .feature-dev/02-contract.json]
    ## Generated cases (from the contract)
    [Insert contents of .feature-dev/06-qa-cases.md]
    ## Implementation
    [Insert contents of .feature-dev/04-backend.md and .feature-dev/05-frontend.md]

    Produce a risk assessment and a test-plan matrix mapping features/fields to
    type (functional/non-functional), level (unit/integration/system/UAT), access
    style (black/white/grey), priority (P0/P1/P2), and owner agent. Tag the smoke
    and regression sets. Dispatch instructions for functional-tester,
    non-functional-tester, and automation-engineer.
```

Save the plan to `.feature-dev/06-qa-plan.md`.

**6.1 — Execute QA and reviews in parallel.** Launch the agents below in a single
response (skip UI-related ones if the feature has no UI):

**6a. Functional testing** (functional, UAT, smoke, regression from the plan + cases):

```
Task:
  subagent_type: "backend-development-functional-tester"
  description: "Functional test cases for $FEATURE"
  prompt: |
    Design and specify functional, UAT, smoke, and regression cases.
    ## QA plan
    [Insert contents of .feature-dev/06-qa-plan.md]
    ## Generated cases
    [Insert contents of .feature-dev/06-qa-cases.md]
    ## Contract
    [Insert full contents of .feature-dev/02-contract.json]
    ## ТЗ acceptance criteria
    [Insert contents of .feature-dev/01-requirements.md]
    Extend the generated cases with UAT scenarios and state-transition cases; tag
    the smoke and regression subsets. Report cases with priority and expected results.
```

**6a-bis. Scenario & requirements cases** (user flows + acceptance criteria, with traceability):

```
Task:
  subagent_type: "backend-development-test-case-designer"
  description: "User-flow and requirements-based cases for $FEATURE"
  prompt: |
    Write scenario-level test cases and a traceability matrix.
    ## ТЗ (acceptance criteria, business rules, roles, flows)
    [Insert contents of .feature-dev/01-requirements.md]
    ## Contract (for entity states)
    [Insert full contents of .feature-dev/02-contract.json]
    ## QA plan
    [Insert contents of .feature-dev/06-qa-plan.md]

    Produce:
    - requirements.json: one entry per ТЗ acceptance criterion / business rule
      ({id, text, priority}) → save to .feature-dev/06-requirements.json
    - cases.json: requirements-based cases (positive/negative/per-role) AND
      user-flow cases (happy / alternative / error paths) and state transitions,
      each with a "covers": [REQ-ids] field → save to .feature-dev/06-scenario-cases.json
    Do not duplicate the field-level contract cases; own scenarios and requirements.
    Report the flows worth automating as E2E (for the automation-engineer).
```

**6b. Non-functional testing** (performance, security, usability, compatibility):

```
Task:
  subagent_type: "backend-development-non-functional-tester"
  description: "Non-functional testing for $FEATURE"
  prompt: |
    Scope and specify non-functional tests per the ТЗ's requirements.
    ## QA plan
    [Insert contents of .feature-dev/06-qa-plan.md]
    ## ТЗ (non-functional requirements)
    [Insert contents of .feature-dev/01-requirements.md]
    ## Contract
    [Insert full contents of .feature-dev/02-contract.json]
    Cover performance (load/stress/spike/soak with thresholds, k6/Locust), security
    (authn/authz per endpoint, input validation/injection targeted by field types),
    usability (primary flows), and compatibility (target browsers/OS/devices).
    Hand deep security to security-auditor (6e) and deep performance to
    performance-engineer (6f).
```

**6c. Test automation** (Playwright + pytest, smoke/regression first):

```
Task:
  subagent_type: "backend-development-automation-engineer"
  description: "Automate tests for $FEATURE"
  prompt: |
    Automate the smoke and regression sets, then broader coverage.
    ## QA plan
    [Insert contents of .feature-dev/06-qa-plan.md]
    ## Generated cases (parametrize from these)
    [Insert contents of .feature-dev/06-qa-cases.json]
    ## Contract
    [Insert full contents of .feature-dev/02-contract.json]
    Use Playwright (E2E/UI, Page Object Model, stable locators) and pytest
    (unit/integration/API, parametrized from the cases). Start from the templates in
    skills/qa-testing-strategy/assets/. Wire CI: smoke on PR, full run nightly.
```

The layer-specific unit/component suites and deep reviews also run in parallel:

**6d. Backend Test Suite:**

```
Task:
  subagent_type: "backend-development-test-automator"
  description: "Create backend test suite for $FEATURE"
  prompt: |
    Create a comprehensive backend test suite for this feature.

    ## What was implemented (backend)
    [Insert contents of .feature-dev/04-backend.md]

    ## Data dictionary contract (assert against this)
    [Insert full contents of .feature-dev/02-contract.json]

    ## Instructions
    1. Write unit tests for all new backend functions/methods
    2. Write integration tests for API endpoints
    3. Assert the API contract: each endpoint returns exactly the fields the
       contract marks for get_index / get_single, and accepts exactly the fields
       marked for create / update — no more, no less. Assert field types match the
       contract's backend types.
    4. Cover: happy path, edge cases, error handling, boundary conditions
    5. Follow existing test patterns and frameworks in the project
    6. Target 80%+ code coverage for new code

    Write all test files. Report what test files were created and what they cover.
```

**6e. UI Test Suite** (skip if no frontend):

```
Task:
  subagent_type: "backend-development-ui-test-automator"
  description: "Create UI test suite for $FEATURE"
  prompt: |
    Create the frontend test suite for this feature, asserting the UI against the
    data-dictionary contract.

    ## What was implemented (frontend)
    [Insert contents of .feature-dev/05-frontend.md]
    ## UI field manifest
    [Insert contents of .feature-dev/05-ui-manifest.json]
    ## Contract (assert against this)
    [Insert full contents of .feature-dev/02-contract.json]

    ## Instructions
    1. Component tests: rendering plus loading/empty/error states.
    2. Contract-alignment tests: table columns == get_index fields; detail ==
       get_single; create form inputs == create fields; edit form == update fields.
       Derive the expected field set from the contract in the test itself.
    3. Validation tests from the contract's required / max / validations.
    4. API-interaction tests with a mocked client: submit posts exactly the allowed
       fields; the list refetches after a successful create/update.
    5. End-to-end tests for the ТЗ's primary journeys.
    6. Accessibility checks (labels, keyboard nav, roles).

    Write all test files. Report coverage and which contract attributes each test verifies.
```

**6f. Security Review:**

```
Task:
  subagent_type: "backend-development-security-auditor"
  description: "Security review of $FEATURE"
  prompt: |
    Perform a security review of this feature implementation.

    ## Architecture
    [Insert contents of .feature-dev/03-architecture.md]

    ## Backend Implementation
    [Insert contents of .feature-dev/04-backend.md]

    ## Frontend Implementation
    [Insert contents of .feature-dev/05-frontend.md]

    Review for: OWASP Top 10, authentication/authorization flaws, input validation gaps,
    data protection issues, dependency vulnerabilities, and any security anti-patterns.

    Provide findings with severity, location, and specific fix recommendations.
```

**6g. Performance Review:**

```
Task:
  subagent_type: "backend-development-performance-engineer"
  description: "Performance review of $FEATURE"
  prompt: |
    Review the performance of this feature implementation.

    ## Architecture
    [Insert contents of .feature-dev/03-architecture.md]

    ## Backend Implementation
    [Insert contents of .feature-dev/04-backend.md]

    ## Frontend Implementation
    [Insert contents of .feature-dev/05-frontend.md]

    Review for: N+1 queries, missing indexes, unoptimized queries, memory leaks,
    missing caching opportunities, large payloads, slow rendering paths.

    Provide findings with impact estimates and specific optimization recommendations.
```

**Traceability gate.** Build the requirement→case→defect matrix and verify every ТЗ
requirement is covered:

```
python skills/qa-testing-strategy/assets/traceability_matrix.py \
    .feature-dev/06-requirements.json .feature-dev/06-scenario-cases.json \
    --markdown .feature-dev/06-traceability.md
```

If it exits non-zero, some ТЗ requirement has no test case (a coverage hole) — STOP,
show the uncovered requirements, and have test-case-designer add the missing cases
before proceeding.

After all QA and review sub-agents complete (functional, scenario/requirements,
non-functional, automation, backend tests, UI tests, security, performance), have
the qa-lead consolidate results into `.feature-dev/06-testing.md`:

```markdown
# Testing & Validation: $FEATURE

## Test Suite

[Summary from 5a — files created, coverage areas]

## Security Findings

[Summary from 5b — findings by severity]

## Performance Findings

[Summary from 5c — findings by impact]

## Action Items

[List any critical/high findings that need to be addressed before delivery]
```

If there are Critical or High severity findings from security or performance review, address them now before proceeding. Apply fixes and re-validate.

Update `state.json`: set `current_step` to "checkpoint-2", add step 6 to `completed_steps`.

---

## PHASE CHECKPOINT 2 — User Approval Required

Display a summary of testing and validation results from `.feature-dev/06-testing.md` and ask:

```
Testing and validation complete. Please review .feature-dev/06-testing.md

Test coverage: [summary]
Security findings: [X critical, Y high, Z medium]
Performance findings: [X critical, Y high, Z medium]

1. Approve — proceed to deployment & documentation
2. Request changes — tell me what to fix
3. Pause — save progress and stop here
```

Do NOT proceed to Phase 3 until the user approves.

---

## Phase 3: Delivery (Steps 6–8)

### Step 7: Deployment & Monitoring

Read `.feature-dev/03-architecture.md` and `.feature-dev/06-testing.md`.

Use the Task tool:

```
Task:
  subagent_type: "general-purpose"
  description: "Create deployment config for $FEATURE"
  prompt: |
    You are a deployment engineer. Create the deployment and monitoring configuration for this feature.

    ## Architecture
    [Insert contents of .feature-dev/03-architecture.md]

    ## Testing Results
    [Insert contents of .feature-dev/06-testing.md]

    ## Instructions
    1. Create or update CI/CD pipeline configuration for the new code
    2. Add feature flag configuration if the feature should be gradually rolled out
    3. Define health checks and readiness probes for new services/endpoints
    4. Create monitoring alerts for key metrics (error rate, latency, throughput)
    5. Write a deployment runbook with rollback steps
    6. Follow existing deployment patterns in the project

    Write all configuration files. Report what was created/modified.
```

Save output to `.feature-dev/07-deployment.md`.

Update `state.json`: set `current_step` to 8, add step 7 to `completed_steps`.

### Step 8: Documentation & Handoff

Read all previous `.feature-dev/*.md` files.

Use the Task tool:

```
Task:
  subagent_type: "general-purpose"
  description: "Write documentation for $FEATURE"
  prompt: |
    You are a technical writer. Create documentation for this feature.

    ## Feature Context
    [Insert contents of .feature-dev/01-requirements.md]

    ## Architecture
    [Insert contents of .feature-dev/03-architecture.md]

    ## Implementation Summary
    ### Backend: [Insert contents of .feature-dev/04-backend.md]
    ### Frontend: [Insert contents of .feature-dev/05-frontend.md]

    ## Deployment
    [Insert contents of .feature-dev/07-deployment.md]

    ## Instructions
    1. Write API documentation for new endpoints (request/response examples)
    2. Update or create user-facing documentation if applicable
    3. Write a brief architecture decision record (ADR) explaining key design choices
    4. Create a handoff summary: what was built, how to test it, known limitations

    Write documentation files. Report what was created/modified.
```

Save output to `.feature-dev/08-documentation.md`.

Update `state.json`: set `current_step` to "complete", add step 8 to `completed_steps`.

---

## Completion

Update `state.json`:

- Set `status` to `"complete"`
- Set `last_updated` to current timestamp

Present the final summary:

```
Feature development complete: $FEATURE

## Files Created
[List all .feature-dev/ output files]

## Implementation Summary
- Requirements: .feature-dev/01-requirements.md
- Database: .feature-dev/02-database.md
- Data dictionary: .feature-dev/02-data-dictionary.xlsx
- Contract (source of truth): .feature-dev/02-contract.json
- Architecture: .feature-dev/03-architecture.md
- Backend: .feature-dev/04-backend.md
- Design tokens: .feature-dev/05-design-tokens.json
- Design mockup: .feature-dev/05-design-mockup.html
- Frontend architecture: .feature-dev/05a-frontend-architecture.md
- Frontend: .feature-dev/05-frontend.md
- UI manifest: .feature-dev/05-ui-manifest.json
- QA plan: .feature-dev/06-qa-plan.md
- QA generated cases: .feature-dev/06-qa-cases.md
- Scenario/requirements cases: .feature-dev/06-scenario-cases.json
- Traceability matrix: .feature-dev/06-traceability.md
- Testing: .feature-dev/06-testing.md
- Deployment: .feature-dev/07-deployment.md
- Documentation: .feature-dev/08-documentation.md

## Next Steps
1. Review all generated code and documentation
2. Run the full test suite to verify everything passes
3. Create a pull request with the implementation
4. Deploy using the runbook in .feature-dev/07-deployment.md
```
