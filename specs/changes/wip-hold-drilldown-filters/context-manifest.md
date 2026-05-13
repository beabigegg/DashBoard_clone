# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/services/wip_service.py
- src/mes_dashboard/sql/wip/detail.sql
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/core/wip-navigation-state.ts
- frontend/src/core/wip-derive.ts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md

## Allowed Paths
- specs/changes/wip-hold-drilldown-filters/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/sql/wip/
- src/mes_dashboard/core/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/tests/components/
- frontend/tests/playwright/
- frontend/tests/legacy/
- frontend/tests/validation/
- contracts/api/
- contracts/data/
- contracts/css/
- contracts/ci/
- tests/

## Required Contracts
- contracts/api/api-contract.md (update — new filter params and lot-row field)
- contracts/api/api-inventory.md (update — WIP-01 rule + filter-options arrays)
- contracts/data/data-shape-contract.md (update — pjType field; workflows/bops/pjFunctions arrays)
- contracts/css/css-contract.md (read-only — confirm no new token/authored-CSS violations)

## Required Tests
- tests/test_wip_routes.py (backend route tests for new filter params and pjType in response)
- frontend/tests/components/FilterPanel.test.js (update filter-group count 6→9; new field labels)
- frontend/tests/components/HoldMatrix.test.js (verify existing drill-down unchanged)
- frontend/tests/playwright/hold-overview.spec.js (existing critical-journey; verify no regression)

## Agent Work Packets

### contract-reviewer
- specs/changes/wip-hold-drilldown-filters/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/services/wip_service.py

### backend-engineer
- specs/changes/wip-hold-drilldown-filters/
- src/mes_dashboard/routes/wip_routes.py
- src/mes_dashboard/services/wip_service.py
- src/mes_dashboard/sql/wip/
- src/mes_dashboard/core/
- tests/

### frontend-engineer
- specs/changes/wip-hold-drilldown-filters/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/tests/components/
- frontend/tests/legacy/
- frontend/tests/validation/

### ci-cd-gatekeeper
- specs/changes/wip-hold-drilldown-filters/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
- frontend/tests/components/
- frontend/tests/playwright/
- tests/

### qa-reviewer
- specs/changes/wip-hold-drilldown-filters/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/core/
- frontend/tests/components/
- frontend/tests/playwright/
- tests/

## Context Expansion Requests
-

## Approved Expansions
-
