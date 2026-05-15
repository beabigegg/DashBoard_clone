---
change-id: hold-history-detail-flat-table
schema-version: 0.1.0
last-changed: 2026-05-15
---

# Implementation Plan: hold-history-detail-flat-table

## Objective

Refactor the Hold/Release 明細 table in hold-history and the Hold Lot Details table in hold-overview from a card-within-card nested layout to a flat flush-edge table, matching the established pattern from hold-detail and wip-detail.

## Execution Scope

### In Scope
- Remove inner `.card-body` padding wrapper around detail DataTable in hold-history
- Remove inner `.card-body` padding wrapper around lot DataTable in hold-overview
- Add `lots-card-body` (padding: 0) scoped CSS class in both apps
- Scope all remaining unscoped CSS rules under `.theme-hold-history` / `.theme-hold-overview`

### Out of Scope
- Backend API changes (payload is already flat)
- Shared DataTable.vue component modifications
- hold-detail or wip-detail changes (reference only)

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | frontend/hold-history | Add `lots-card-body` class to detail card body; remove extra padding wrapper | frontend-engineer |
| IP-2 | frontend/hold-overview | Add `lots-card-body` class to lot details card body; remove extra padding wrapper | frontend-engineer |
| IP-3 | css/hold-history | Add `.theme-hold-history .lots-card-body { padding: 0 }` scoped rule | frontend-engineer |
| IP-4 | css/hold-overview | Add `.theme-hold-overview .lots-card-body { padding: 0 }` scoped rule | frontend-engineer |
| IP-5 | css/hold-history | Scope all remaining unscoped rules under `.theme-hold-history` | frontend-engineer |
| IP-6 | css/hold-overview | Scope all remaining unscoped rules under `.theme-hold-overview` | frontend-engineer |
| IP-7 | contracts/css | Update css-contract.md Detail Table Layout Rule to include hold-history and hold-overview | contract-reviewer |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| frontend/src/hold-history/components/DetailTable.vue | modify template | Add `lots-card-body` to card-body div wrapping DataTable |
| frontend/src/hold-overview/App.vue | modify template | Add `lots-card-body` to card-body div wrapping lot DataTable |
| frontend/src/hold-history/style.css | modify | Add `.lots-card-body { padding: 0 }`; scope all rules under `.theme-hold-history` |
| frontend/src/hold-overview/style.css | modify | Add `.lots-card-body { padding: 0 }`; scope all rules under `.theme-hold-overview` |
| contracts/css/css-contract.md | update | Add hold-history and hold-overview to Detail Table Layout Rule table |

## Contract Updates

- API: no change
- CSS/UI: css-contract.md Detail Table Layout Rule — add hold-history (Hold/Release 明細) and hold-overview (Hold Lot Details)
- Env: no change
- Data shape: no change
- Business logic: no change
- CI/CD: no change

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 flat table in hold-history | frontend/tests/playwright/hold-history.spec.js | no nested card-body padding |
| AC-2 flat table in hold-overview | frontend/tests/playwright/hold-overview.spec.js | no nested card-body padding |
| AC-3 existing columns/sorting/pagination | npm run test | 0 regressions |
| AC-4 API payload unchanged | tests/e2e/test_hold_history_e2e.py | backend read-only verified |
| AC-5 DataTable.vue not modified | npm run type-check | 0 errors |
| AC-6 existing E2E selectors pass | npm run css:check | 0 errors |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- Portal-shell CSS injection caches bundles permanently in `<head>`; unscoped rules from any bundle bleed into other pages. All CSS changes must be scoped under `.theme-*` root class to prevent regression on page switching.
