# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend-components (new shared `AsyncQueryProgress.vue`)
- frontend-composables (`useAsyncJobPolling.ts` type fix; `useProductionHistory.ts` wiring)
- frontend-consumers (`yield-alert-center/App.vue`, `production-history/App.vue`)
- backend-services (`yield_alert_job_service.py`, `production_history_job_service.py` pct milestones)

## Allowed Paths
- specs/changes/async-progress-ui/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/
- frontend/src/yield-alert-center/
- frontend/src/production-history/
- frontend/src/reject-history/
- frontend/tests/components/
- frontend/tests/shared-composables/
- src/mes_dashboard/services/
- tests/
- contracts/css/
- contracts/data/
- contracts/api/
- .github/workflows/

## Required Contracts
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/api/api-contract.md (no-change confirmation only)

## Required Tests
- frontend/tests/components/ (new AsyncQueryProgress.vue unit tests)
- frontend/tests/shared-composables/useAsyncJobPolling.test.js (extend for pct/stage types)
- tests/ (backend pct-milestone tests for the two job services)

## Agent Work Packets

### contract-reviewer
- specs/changes/async-progress-ui/
- contracts/css/
- contracts/data/
- contracts/api/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/

### test-strategist
- specs/changes/async-progress-ui/
- frontend/tests/components/
- frontend/tests/shared-composables/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/

### ci-cd-gatekeeper
- specs/changes/async-progress-ui/
- .github/workflows/

### implementation-planner
- specs/changes/async-progress-ui/
- specs/context/project-map.md
- specs/context/contracts-index.md

### frontend-engineer
- specs/changes/async-progress-ui/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/
- frontend/src/yield-alert-center/
- frontend/src/production-history/
- frontend/src/reject-history/
- frontend/tests/components/
- frontend/tests/shared-composables/
- contracts/css/

### backend-engineer
- specs/changes/async-progress-ui/
- src/mes_dashboard/services/
- tests/

### ui-ux-reviewer
- specs/changes/async-progress-ui/
- frontend/src/shared-ui/components/
- frontend/src/yield-alert-center/
- frontend/src/production-history/

### visual-reviewer
- specs/changes/async-progress-ui/
- frontend/src/shared-ui/components/
- frontend/src/yield-alert-center/
- frontend/src/production-history/

### qa-reviewer
- specs/changes/async-progress-ui/

## Context Expansion Requests
-

## Approved Expansions
-
