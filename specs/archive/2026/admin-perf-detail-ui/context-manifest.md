# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- admin-dashboard SPA performance-detail tab (frontend/src/admin-dashboard/tabs/) — not admin-pages

## Allowed Paths
- specs/changes/admin-perf-detail-ui/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/admin-dashboard/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/src/core/
- frontend/src/shared-ui/
- frontend/src/styles/
- frontend/tailwind.config.js
- frontend/vitest.config.js
- frontend/tests/
- contracts/api/api-contract.md
- contracts/css/css-inventory.md
- contracts/css/css-contract.md
- .github/workflows/

## Required Contracts
- contracts/api/api-contract.md (read-only: confirm 6 fields already documented from fix-admin-dashboard)

## Required Tests
- frontend/tests/ (new Vitest unit tests for performance-detail rendering)

## Agent Work Packets

### change-classifier
- specs/changes/admin-perf-detail-ui/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/admin-perf-detail-ui/
- contracts/api/api-contract.md
- contracts/css/css-inventory.md
- contracts/css/css-contract.md

### test-strategist
- specs/changes/admin-perf-detail-ui/

### ci-cd-gatekeeper
- specs/changes/admin-perf-detail-ui/
- .github/workflows/
- contracts/ci/

### implementation-planner
- specs/changes/admin-perf-detail-ui/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/src/core/
- contracts/api/api-contract.md

### frontend-engineer
- specs/changes/admin-perf-detail-ui/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/src/core/
- frontend/src/shared-ui/
- frontend/src/styles/
- frontend/tailwind.config.js
- frontend/vitest.config.js
- frontend/tests/
- contracts/api/api-contract.md

### ui-ux-reviewer
- specs/changes/admin-perf-detail-ui/
- frontend/src/admin-pages/
- frontend/src/shared-ui/
- contracts/css/css-contract.md

### qa-reviewer
- specs/changes/admin-perf-detail-ui/

## Context Expansion Requests
-

## Approved Expansions
- id: CER-1
  approved-by: main-claude
  paths:
    - frontend/src/admin-dashboard/
  reason: Performance-detail view lives in admin-dashboard/tabs/ (PerformanceTab.vue), not admin-pages/. Confirmed by implementation-planner grep for performance-detail / evicted_keys / slowlog.
