# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/reject-history/App.vue
- frontend/src/reject-history/main.js → main.ts
- frontend/src/reject-history/useRejectHistoryDuckDB.js → useRejectHistoryDuckDB.ts
- frontend/src/reject-history/components/DetailTable.vue
- frontend/src/reject-history/components/FilterPanel.vue
- frontend/src/reject-history/components/ParetoGrid.vue
- frontend/src/reject-history/components/ParetoSection.vue
- frontend/src/reject-history/components/SummaryCards.vue
- frontend/src/reject-history/components/TrendChart.vue
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py

## Allowed Paths
- specs/changes/migrate-reject-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/reject-history/
- frontend/src/reject-history/components/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/admin-shared/
- frontend/src/resource-shared/
- frontend/src/wip-shared/
- frontend/tests/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/package.json
- contracts/ci/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- CLAUDE.md
- ts-migration-plan.md

## Required Contracts
- contracts/ci/ci-gate-contract.md — expand frontend-type-check scope to include src/reject-history/**/*; bump schema-version to 1.3.5

## Required Tests
- frontend/tests/abort/reject-history-abort.test.js
- frontend/tests/components/ParetoGrid.test.js
- frontend/tests/legacy/reject-history-date-range-limit.test.js
- frontend/tests/validation/useRejectHistory.validation.test.js
- frontend/tests/playwright/reject-history.spec.js
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py

## Agent Work Packets

### change-classifier
- specs/changes/migrate-reject-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-reject-history-ts/
- contracts/ci/
- frontend/tsconfig.json

### test-strategist
- specs/changes/migrate-reject-history-ts/
- frontend/tests/
- frontend/src/reject-history/
- frontend/src/reject-history/components/

### frontend-engineer
- specs/changes/migrate-reject-history-ts/
- frontend/src/reject-history/
- frontend/src/reject-history/components/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/admin-shared/
- frontend/src/resource-shared/
- frontend/src/wip-shared/
- frontend/tests/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/package.json
- contracts/ci/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- CLAUDE.md
- ts-migration-plan.md

### ci-cd-gatekeeper
- specs/changes/migrate-reject-history-ts/
- contracts/ci/
- frontend/tsconfig.json
- frontend/package.json

### qa-reviewer
- specs/changes/migrate-reject-history-ts/
- frontend/src/reject-history/
- frontend/src/reject-history/components/
- frontend/tests/
- contracts/ci/

## Context Expansion Requests
-

## Approved Expansions
-
