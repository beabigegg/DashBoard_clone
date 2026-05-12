# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/admin-shared/
- frontend/src/admin-dashboard/
- frontend/src/admin-performance/
- frontend/src/admin-user-usage-kpi/
- frontend/tsconfig.json
- frontend/tests/legacy/
- frontend/tests/components/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py

## Allowed Paths
- specs/changes/migrate-admin-shared-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- specs/archive/2026/migrate-shared-ui-ts/
- CLAUDE.md
- ts-migration-plan.md
- frontend/src/admin-shared/
- frontend/src/admin-dashboard/
- frontend/src/admin-performance/
- frontend/src/admin-user-usage-kpi/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- frontend/scripts/ts-resolver-loader.mjs
- frontend/scripts/css-governance-check.js
- frontend/tests/legacy/
- frontend/tests/components/
- frontend/tests/shared-composables/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/ci/ci-gate-contract.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml
- environment.yml

## Required Contracts
- contracts/css/css-inventory.md
- contracts/css/css-contract.md
- contracts/ci/ci-gate-contract.md

## Required Tests
- frontend/tests/legacy/admin-dashboard.test.js
- frontend/tests/legacy/admin-performance.test.js
- frontend/tests/legacy/admin-user-usage-kpi.test.js
- frontend/tests/components/ (any test touching admin-shared components)
- cd frontend && npm run type-check
- cd frontend && npm run test
- cd frontend && npm run build
- cd frontend && npm run css:check
- pytest tests/test_frontend_compute_parity.py tests/test_frontend_duckdb_parity.py

## Agent Work Packets

### change-classifier
- specs/changes/migrate-admin-shared-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-admin-shared-ts/
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/ci/ci-gate-contract.md
- frontend/src/admin-shared/

### test-strategist
- specs/changes/migrate-admin-shared-ts/
- frontend/src/admin-shared/
- frontend/tests/legacy/
- frontend/tests/components/
- frontend/tests/shared-composables/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- frontend/tsconfig.json
- frontend/vitest.config.js

### frontend-engineer
- specs/changes/migrate-admin-shared-ts/
- specs/archive/2026/migrate-shared-ui-ts/
- CLAUDE.md
- ts-migration-plan.md
- frontend/src/admin-shared/
- frontend/src/admin-dashboard/
- frontend/src/admin-performance/
- frontend/src/admin-user-usage-kpi/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/scripts/ts-resolver-loader.mjs
- frontend/tests/legacy/
- frontend/tests/components/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py

### ci-cd-gatekeeper
- specs/changes/migrate-admin-shared-ts/
- contracts/ci/ci-gate-contract.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml
- frontend/package.json
- environment.yml

### qa-reviewer
- specs/changes/migrate-admin-shared-ts/
- frontend/src/admin-shared/
- frontend/tests/legacy/
- frontend/tests/components/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py

## Context Expansion Requests
-

## Approved Expansions
-
