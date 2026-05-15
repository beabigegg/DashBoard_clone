# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend-ui: `frontend/src/reject-history/` (DetailTable.vue, App.vue, style.css), `frontend/src/material-trace/` (App.vue, style.css)
- css: scoped styles in above components

## Allowed Paths
- specs/changes/reject-material-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- frontend/src/shared-ui/components/
- frontend/src/styles/
- tests/e2e/
- frontend/tests/playwright/

## Required Contracts
- `contracts/css/css-contract.md` — add reject-history DetailTable.vue and material-trace Result detail table to Detail Table Layout Rule table
- All other contracts: no change

## Required Tests
- CSS governance: `npm run css:check`
- Vitest: `npm run test`
- Playwright E2E: new `frontend/tests/playwright/reject-material-flat-table.spec.js`
- Type check (informational): `npm run type-check`

## Agent Work Packets

### change-classifier
- specs/changes/reject-material-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/reject-material-flat-table/
- contracts/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-history/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

### test-strategist
- specs/changes/reject-material-flat-table/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/tests/playwright/
- contracts/

### frontend-engineer
- specs/changes/reject-material-flat-table/
- contracts/css/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-history/
- frontend/src/hold-detail/
- frontend/src/wip-detail/
- frontend/src/shared-ui/components/
- frontend/src/styles/

### ui-ux-reviewer
- specs/changes/reject-material-flat-table/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

### visual-reviewer
- specs/changes/reject-material-flat-table/
- frontend/src/reject-history/
- frontend/src/material-trace/
- frontend/src/hold-detail/
- frontend/src/wip-detail/

### ci-cd-gatekeeper
- specs/changes/reject-material-flat-table/
- contracts/ci/

### qa-reviewer
- specs/changes/reject-material-flat-table/
- frontend/src/reject-history/
- frontend/src/material-trace/
- tests/e2e/
- frontend/tests/playwright/

## Context Expansion Requests
-

## Approved Expansions
-
