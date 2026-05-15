---
change-id: reject-material-flat-table
schema-version: 0.1.0
last-changed: 2026-05-15
---

# Implementation Plan: reject-material-flat-table

## Objective

Apply the flat flush-edge DataTable layout (pattern proven by hold-history-detail-flat-table) to reject-history and material-trace by adding a `padding: 0` override to the card body that wraps each detail DataTable.

## Execution Scope

### In Scope
- Add scoped `lots-card-body` (padding: 0) CSS class to reject-history detail card body
- Add scoped `lots-card-body` (padding: 0) CSS class to material-trace result detail card body
- Scope all remaining unscoped CSS rules in reject-history/style.css and material-trace/style.css

### Out of Scope
- Backend API changes
- Shared DataTable.vue component modifications
- TypeScript migration for material-trace (JS SFC — template/style changes only)

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | css/reject-history | Add `.theme-reject-history .lots-card-body { padding: 0 }` and scope all unscoped rules | frontend-engineer |
| IP-2 | css/material-trace | Add `.theme-material-trace .lots-card-body { padding: 0 }` and scope all unscoped rules | frontend-engineer |
| IP-3 | frontend/reject-history | Add `lots-card-body` class to card-body wrapping detail DataTable | frontend-engineer |
| IP-4 | frontend/material-trace | Add `lots-card-body` class to card-body wrapping result DataTable | frontend-engineer |
| IP-5 | contracts/css | Update css-contract.md Detail Table Layout Rule to include reject-history and material-trace | contract-reviewer |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| frontend/src/reject-history/style.css | modify | Add `.lots-card-body { padding: 0 }`; scope remaining rules under `.theme-reject-history` |
| frontend/src/material-trace/style.css | modify | Add `.lots-card-body { padding: 0 }`; scope remaining rules under `.theme-material-trace` |
| frontend/src/reject-history/components/DetailTable.vue | modify template | Add `lots-card-body` class to card-body div |
| frontend/src/material-trace/App.vue | modify template | Add `lots-card-body` class to card-body div wrapping DataTable |
| contracts/css/css-contract.md | update | Add reject-history and material-trace to Detail Table Layout Rule table |

## Contract Updates

- API: no change
- CSS/UI: css-contract.md Detail Table Layout Rule — add reject-history (Hold/Release 明細) and material-trace (Result detail)
- Env: no change
- Data shape: no change
- Business logic: no change
- CI/CD: no change

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 flat table in reject-history | frontend/tests/playwright/reject-history.spec.js | DataTable flush against card edge |
| AC-2 flat table in material-trace | frontend/tests/playwright/material-trace.spec.js | DataTable flush against card edge |
| AC-3 css:check passes | npm run css:check | 0 errors |
| AC-4 Vitest passes | npm run test | 331 tests, 0 regressions |
| AC-5 no API change | tests/e2e/ | backend read-only verified |
| AC-6 other card content unaffected | visual review | headers/toolbars/filters visually intact |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- material-trace/App.vue is a non-migrated JS SFC; changes are template/style-only. Do not introduce TypeScript syntax.
- Portal-shell CSS injection caches all bundles permanently; all new rules must be scoped under `.theme-*` to prevent bleed on page switching.
