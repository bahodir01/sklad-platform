# Design system & accessibility

Baseline design tokens, layout rules, and accessibility requirements the frontend
agents apply. These keep generated UI consistent and usable regardless of
framework. Match an existing project's design system when one is present — this is
the fallback, not an override.

## Tokens

Define tokens once (CSS variables, a theme file, or the framework's system) and
reference them everywhere — no hard-coded colors or spacing in components.

- **Spacing scale** — a single scale (e.g. 4/8/12/16/24/32/48) used for margin,
  padding, and gaps. Don't invent one-off values.
- **Typography** — a small type scale (display / heading / body / caption) with
  defined line-heights; one or two families.
- **Color** — semantic roles (`surface`, `text`, `primary`, `muted`, `success`,
  `warning`, `danger`) rather than raw hex in components. Ensure text/background
  pairs meet WCAG AA contrast (4.5:1 for body text).
- **Radius / elevation** — a couple of radii and shadow levels, applied
  consistently.

## Layout

- Mobile-first; layouts adapt up. Use the framework's grid/flex utilities rather
  than absolute positioning.
- Constrain content width for readability; don't let forms sprawl full-width on
  large screens.
- Consistent page scaffold: header / content / actions in the same places across
  screens.

## Component states

Every data-bound component handles four states explicitly:

- **Loading** — skeletons or spinners, not a blank screen.
- **Empty** — a clear empty state with the next action.
- **Error** — a readable message and a retry path; surface backend field errors on
  the matching inputs (by contract attribute name).
- **Success/data** — the normal render.

## Forms

- Every input has a visible, associated `<label>` (`for`/`id` or wrapping).
- Show validation inline, near the field, on blur or submit — not only a summary.
- Disable submit while pending; prevent double submit.
- Required fields marked visually and programmatically (`aria-required`).
- Map server validation errors back to fields by contract attribute name.

## Accessibility (structural, not optional)

- Semantic elements: `<button>` for actions, `<a>` for navigation, headings in
  order, `<table>` for tabular data.
- All interactive elements reachable and operable by keyboard; visible focus.
- Labels for inputs; `aria-*` only to fill gaps semantics can't, not as a
  substitute for semantic markup.
- Color is never the sole signal (pair with text/icon).
- Respect reduced-motion preferences for animation.

## Tables / lists

- Column set comes from the contract's `get_index` attributes; use the attribute
  `label` for headers.
- Format by type: numbers right-aligned, dates in a consistent locale format,
  booleans as a clear yes/no or icon-with-text.
- Provide sorting/filtering only for fields the contract marks as filterable
  (`filter`), and pagination for large lists.

## What to avoid

- Hard-coded field lists — generate from the contract so drift is impossible.
- Inline styles with magic numbers — use tokens.
- Div-buttons and click handlers on non-interactive elements.
- Client-only validation as the sole guard — the backend enforces the same rules.
