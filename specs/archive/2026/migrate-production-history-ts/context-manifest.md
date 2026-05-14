# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/production-history/main.js → main.ts
- frontend/src/production-history/App.vue (lang="ts")
- frontend/src/production-history/composables/useProductionHistory.js → useProductionHistory.ts
- frontend/src/production-history/components/ProductionMatrix.vue (lang="ts")
- frontend/src/production-history/components/ProductionDetailTable.vue (lang="ts")
- frontend/tests/abort/production-history-abort.test.js (audit for require()/imports)
- frontend/tests/legacy/production-history.test.js (audit for readSource regex + .js paths)
- frontend/tests/validation/useProductionHistory.validation.test.js (audit for .js imports)
- tests/test_*_parity.py (audit for production-history .js paths)
- tests/test_*_safety.py (audit for production-history .js paths)
- frontend/src/production-history/index.html (verify NOT modified — Vite resolves main.ts)

## Allowed Paths
- specs/changes/migrate-production-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- CLAUDE.md
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/abort/
- frontend/tests/legacy/
- frontend/tests/validation/
- frontend/tests/components/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- tests/
- contracts/ci/
- contracts/css/

## Required Contracts
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md

## Required Tests
- frontend/tests/abort/production-history-abort.test.js
- frontend/tests/legacy/production-history.test.js
- frontend/tests/validation/useProductionHistory.validation.test.js
- tests/test_frontend_compute_parity.py (audit)
- tests/test_frontend_duckdb_parity.py (audit)
- tests/test_*_frontend_safety.py (audit any production-history references)
- tests/e2e/test_production_history_e2e.py

## Agent Work Packets

### change-classifier
- specs/changes/migrate-production-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- CLAUDE.md

### frontend-engineer
- specs/changes/migrate-production-history-ts/
- CLAUDE.md
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/abort/
- frontend/tests/legacy/
- frontend/tests/validation/
- frontend/tests/components/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- tests/

### ci-cd-gatekeeper
- specs/changes/migrate-production-history-ts/
- contracts/ci/
- frontend/package.json
- frontend/tsconfig.json

### qa-reviewer
- specs/changes/migrate-production-history-ts/
- frontend/src/production-history/
- tests/

## Context Expansion Requests
-

## Approved Expansions
-
