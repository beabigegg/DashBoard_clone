# Tailwind Style Governance (Migration Phase)

## Scope

- Applies to all new frontend work under `frontend/src/**` during iframe removal migration.
- Existing page-local CSS can remain temporarily, but new large page-local blocks are disallowed.

## Rules

1. New shared UI styles must be authored in Tailwind layers (`base`, `components`, `utilities`) under `frontend/src/styles/tailwind.css`.
2. Reusable patterns (cards, filter bars, badge groups, table shells) must use component classes or Vue components, not copy-pasted CSS.
3. Page-specific CSS additions over 40 lines require an explicit migration note in the PR and an issue to move them into shared layers.
4. Token values must come from `tailwind.config.js` or CSS variables in `tailwind.css`; hard-coded new color scales are disallowed.
5. Motion/accessibility styles must support reduced-motion fallback and avoid forced animation on critical data refresh paths.

## Review Checklist

- New files import `frontend/src/styles/tailwind.css` through the entry module.
- No new iframe-targeting selectors are introduced.
- Shared classes/components are reused before adding page-local CSS.
- Token naming remains stable (`brand`, `surface`, `stroke`, `state`, spacing/radius/shadow/z-index).

## Exceptions

- Bugfix hotfixes may temporarily bypass these rules only if release risk is high.
- Every exception must include an expiry task in `openspec/changes/portal-no-iframe-navigation/tasks.md`.
