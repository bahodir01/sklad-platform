---
name: frontend-component-design
description: Turn the ТЗ and the database-architect's data-dictionary contract into frontend structure and component code — component tree, forms, tables, typed API layer, and tests. Use when designing or implementing UI for a feature, generating forms/tables from a schema contract, building a typed API-integration layer, or verifying that UI fields match the contract. Framework-agnostic (React/Vue/Angular), chosen from the ТЗ.
---

# Frontend Component Design

Build the client side of a feature from the same contract the backend uses, so the
UI, the API calls, and the database schema can never disagree. This is the mirror
of the backend flow: where the backend generates models and serializers from
`contract.json`, the frontend generates forms, tables, and typed clients from it.

## When to Use This Skill

- Designing UI architecture (component tree, routing, state) from the ТЗ
- Implementing forms and tables from the data-dictionary contract
- Generating a typed API-integration layer (types, clients, hooks) from the contract
- Writing UI tests that assert the components match the contract
- Verifying that a built UI uses only contract fields with correct exposure

## Framework selection (from the ТЗ, not a blind default)

Choose per the ТЗ and existing codebase; state the rationale.

- **React** — default for component SPAs; pair with a query cache (React Query).
- **Vue** — when preferred or for progressive reactivity; Vue Query for caching.
- **Angular** — when mandated or for batteries-included enterprise apps.
- **Language** — TypeScript by default (the contract has concrete types worth
  enforcing at compile time); plain JS only when the project requires it.

Never introduce a second framework into an existing codebase.

## The contract is the source of truth

`02-contract.json` (produced by database-architect) drives the UI:

- **Field names** in forms, tables, and payloads match contract attribute names
  EXACTLY — never invented or renamed.
- **Form controls** come from each attribute's frontend block: `input_type`,
  `required`, `max`, `disabled`, `validations`, and the choice source
  (`choice_model` / `choice_enum`). Honor the frontend value when it differs from
  the backend.
- **Exposure by API flag**: tables/lists render `get_index` attributes; detail
  views render `get_single`; create forms include exactly the `create` fields;
  edit forms include exactly the `update` fields.
- **Types** line up with the contract's backend types (see the type map in
  `references/contract-to-ui.md`).

Generate forms and tables *from the contract data* rather than hand-listing fields,
so drift is impossible by construction.

## Workflow

1. **Architect** — read the ТЗ and contract; choose the framework; design the
   component tree, routing, state strategy, and a data-binding plan mapping each
   screen/form to contract attributes.
2. **Integrate** — generate entity/payload/read types and a typed API client
   (functions + hooks/services) from the contract and the backend endpoints.
3. **Implement** — build components, tables, and forms from the plan and the typed
   client, with loading/empty/error states and accessibility built in.
4. **Test** — write component, contract-alignment, validation, and end-to-end
   tests that assert the UI matches the contract.
5. **Verify** — run `assets/ui_contract_validator.py` against the built UI's field
   manifest to catch any field not in the contract or any write field exposed
   against the API flags.

## Verifying the UI against the contract

The frontend can't be AST-parsed across every framework, so the check works on a
small **field manifest** the frontend developer emits — a JSON list of what each
view/form renders. The validator compares it to the contract:

```bash
python assets/ui_contract_validator.py contract.json ui_manifest.json
```

It fails (exit 1) if a view references a field not in the contract, a table shows a
non-`get_index` field, or a create/edit form includes a field not flagged
`create`/`update`. See `references/contract-to-ui.md` for the manifest format.

## Best Practices

- Keep presentational components pure; fetch in containers/hooks.
- Derive validation from the contract; don't re-invent rules already in the dict.
- Cache server data and invalidate on write so the UI reflects changes.
- Design empty/loading/error states for every data-bound view.
- Accessibility is structural: semantic elements, labels tied to inputs, keyboard
  paths — from the start, not bolted on.
- Don't send a read-only field in a create payload; split read/create/update types
  by the API flags.

Design tokens, layout, typography, and accessibility details are in
`references/design-system.md`. The contract→UI type map, control mapping, and
manifest format are in `references/contract-to-ui.md`.
