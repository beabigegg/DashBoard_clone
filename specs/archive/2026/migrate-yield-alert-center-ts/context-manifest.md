# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/yield-alert-center/ (main.js, utils.js, useYieldAlertDuckDB.js, App.vue, YieldHeatmap.vue, YieldPackageChart.vue, YieldStationChart.vue, YieldTrendChart.vue)
- frontend/tests/yield-alert/App.cross-filter.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/abort/yield-alert-abort.test.js

## Allowed Paths
- specs/changes/migrate-yield-alert-center-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/yield-alert-center/
- frontend/tests/yield-alert/
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/src/core/shell-navigation.ts
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/src/resource-shared/
- contracts/
- tests/test_frontend_duckdb_parity.py
- .github/workflows/
- frontend/tsconfig.json
- frontend/vitest.config.js

## Required Contracts
-

## Required Tests
- frontend/tests/yield-alert/App.cross-filter.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/validation/useYieldAlert.validation.test.js

## Agent Work Packets

### change-classifier
- specs/changes/migrate-yield-alert-center-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-yield-alert-center-ts/
- contracts/
- frontend/src/yield-alert-center/

### test-strategist
- specs/changes/migrate-yield-alert-center-ts/
- frontend/tests/yield-alert/
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/validation/useYieldAlert.validation.test.js
- tests/test_frontend_duckdb_parity.py

### frontend-engineer
- specs/changes/migrate-yield-alert-center-ts/
- frontend/src/yield-alert-center/
- frontend/tests/yield-alert/
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/src/core/shell-navigation.ts
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/src/resource-shared/
- tests/test_frontend_duckdb_parity.py

### ci-cd-gatekeeper
- specs/changes/migrate-yield-alert-center-ts/
- .github/workflows/
- frontend/tsconfig.json
- frontend/vitest.config.js

### qa-reviewer
- specs/changes/migrate-yield-alert-center-ts/
- frontend/src/yield-alert-center/
- frontend/tests/yield-alert/
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/abort/yield-alert-abort.test.js

## Context Expansion Requests
-

## Approved Expansions
-
