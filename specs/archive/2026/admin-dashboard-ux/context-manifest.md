# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- admin-dashboard feature app (OverviewTab, WorkerTab, CacheTab, and all tabs that call refresh())
- admin-shared component library (SummaryCard, TrendChart, and shared composables)

## Allowed Paths
- specs/changes/admin-dashboard-ux/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/admin-dashboard/
- frontend/src/admin-shared/
- frontend/src/shared-ui/components/SummaryCard.vue
- frontend/tests/components/
- frontend/package.json
- frontend/vitest.config.js
- contracts/css/css-inventory.md
- contracts/css/css-contract.md

## Required Contracts
- none

## Required Tests
- frontend/src/admin-dashboard/tabs/__tests__/
- frontend/src/admin-shared/components/__tests__/ (new)

## Agent Work Packets

### change-classifier
- specs/changes/admin-dashboard-ux/
- specs/context/project-map.md
- specs/context/contracts-index.md

### implementation-planner
- specs/changes/admin-dashboard-ux/
- frontend/src/admin-dashboard/
- frontend/src/admin-shared/

### test-strategist
- specs/changes/admin-dashboard-ux/
- frontend/src/admin-dashboard/
- frontend/src/admin-shared/
- frontend/vitest.config.js

### frontend-engineer
- specs/changes/admin-dashboard-ux/
- frontend/src/admin-dashboard/
- frontend/src/admin-shared/
- frontend/vitest.config.js

### contract-reviewer
- specs/changes/admin-dashboard-ux/
- contracts/css/css-inventory.md
- contracts/css/css-contract.md

### ui-ux-reviewer
- specs/changes/admin-dashboard-ux/
- frontend/src/admin-dashboard/
- frontend/src/admin-shared/

### qa-reviewer
- specs/changes/admin-dashboard-ux/

## Context Expansion Requests
-

## Approved Expansions
-
