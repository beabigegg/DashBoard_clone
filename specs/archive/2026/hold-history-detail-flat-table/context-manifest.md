# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend-ui: `frontend/src/hold-history/` (DetailTable.vue, App.vue), `frontend/src/hold-overview/` (App.vue, components/)
- css: scoped styles in above components, `frontend/src/hold-history/style.css`, `frontend/src/hold-overview/style.css`
- tests: `tests/e2e/test_hold_history_e2e.py`, `tests/e2e/test_hold_overview_e2e.py`, `frontend/tests/playwright/hold-overview.spec.js`, `frontend/tests/validation/useHoldOverview.validation.test.js`
- backend-api: read-only verification of `src/mes_dashboard/routes/hold_history_routes.py`, `hold_overview_routes.py`, `services/hold_history_service.py`

## Allowed Paths
- specs/changes/hold-history-detail-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- frontend/src/shared-ui/components/
- frontend/src/styles/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- tests/e2e/
- frontend/tests/playwright/
- frontend/tests/validation/
- contracts/

## Required Contracts
- `contracts/css/css-contract.md` — update to specify hold-history Hold/Release 明細 and hold-overview Hold Lot Details render as single flat tables matching hold-detail / wip-detail pattern
- All other contracts: no change

## Required Tests
- E2E: `tests/e2e/test_hold_history_e2e.py`, `tests/e2e/test_hold_overview_e2e.py` (update selectors if needed)
- Playwright: `frontend/tests/playwright/hold-overview.spec.js`
- Validation: `frontend/tests/validation/useHoldOverview.validation.test.js`
- CSS governance: `npm run css:check`
- Type check: `npm run type-check`

## Agent Work Packets

### contract-reviewer
- specs/changes/hold-history-detail-flat-table/
- contracts/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

### test-strategist
- specs/changes/hold-history-detail-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- tests/e2e/
- frontend/tests/playwright/
- frontend/tests/validation/
- contracts/

### frontend-engineer
- specs/changes/hold-history-detail-flat-table/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- frontend/src/shared-ui/components/
- frontend/src/styles/
- contracts/

### ui-ux-reviewer
- specs/changes/hold-history-detail-flat-table/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

### visual-reviewer
- specs/changes/hold-history-detail-flat-table/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

### ci-cd-gatekeeper
- specs/changes/hold-history-detail-flat-table/
- contracts/ci/

### qa-reviewer
- specs/changes/hold-history-detail-flat-table/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- tests/e2e/
- frontend/tests/playwright/
- frontend/tests/validation/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/

## Context Expansion Requests
-

## Approved Expansions
-
