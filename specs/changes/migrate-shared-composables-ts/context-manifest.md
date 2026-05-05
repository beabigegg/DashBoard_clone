# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/shared-composables/ (11 .js files + index.js + 1 .vue)
- frontend/tests/shared-composables/ (3 existing Vitest suites)
- frontend/tsconfig.json (include scope expansion)
- frontend/src/<feature-apps>/ (compile-time consumers — read-only verification of imports)
- tests/**/*.py (Python parity-test audit per CLAUDE.md TypeScript Migration Rules)

## Allowed Paths
- specs/changes/migrate-shared-composables-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/shared-composables/
- frontend/tests/legacy/query-tool-composables.test.js
- frontend/tests/legacy/material-trace-composables.test.js
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/tests/abort/production-history-abort.test.js
- frontend/tests/abort/reject-history-abort.test.js
- frontend/tests/abort/query-tool-abort.test.js
- frontend/tests/core/api-dedup.test.js
- frontend/src/wip-shared/composables/useAutoRefresh.js
- frontend/src/wip-shared/composables/useAutocomplete.js
- contracts/CHANGELOG.md
- frontend/tsconfig.json
- frontend/package.json
- frontend/vitest.config.js
- frontend/vite.config.ts
- frontend/scripts/ts-resolver-loader.mjs
- contracts/ci/ci-gate-contract.md
- .github/workflows/frontend-tests.yml
- ts-migration-plan.md
- CLAUDE.md
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py

## Required Contracts
- contracts/ci/ci-gate-contract.md (read-only confirmation that gate set is unchanged beyond type-check scope)

## Required Tests
- frontend/tests/shared-composables/useAsyncJobPolling.test.js
- frontend/tests/shared-composables/useAutoRefresh.test.js
- frontend/tests/shared-composables/useRequestGuard.test.js
- frontend/tests/legacy/query-tool-composables.test.js
- frontend/tests/legacy/material-trace-composables.test.js
- frontend/tests/legacy/mid-section-defect-composables.test.js

## Agent Work Packets

### change-classifier
- specs/changes/migrate-shared-composables-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-shared-composables-ts/
- contracts/ci/ci-gate-contract.md
- frontend/tsconfig.json

### test-strategist
- specs/changes/migrate-shared-composables-ts/
- frontend/src/shared-composables/
- frontend/tests/shared-composables/
- frontend/tests/legacy/query-tool-composables.test.js
- frontend/tests/legacy/material-trace-composables.test.js
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/package.json
- frontend/vitest.config.js
- frontend/tsconfig.json

### frontend-engineer
- specs/changes/migrate-shared-composables-ts/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/shared-composables/
- frontend/tsconfig.json
- frontend/package.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/scripts/ts-resolver-loader.mjs
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- ts-migration-plan.md

### ci-cd-gatekeeper
- specs/changes/migrate-shared-composables-ts/
- contracts/ci/ci-gate-contract.md
- .github/workflows/frontend-tests.yml
- frontend/package.json
- frontend/tsconfig.json

### qa-reviewer
- specs/changes/migrate-shared-composables-ts/
- contracts/ci/ci-gate-contract.md

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - frontend/src/wip-overview/
    - frontend/src/hold-history/
    - frontend/src/query-tool/
    - frontend/src/reject-history/
    - frontend/src/production-history/
    - frontend/src/yield-alert-center/
    - frontend/src/portal-shell/
  reason: frontend-engineer may need to grep feature-app imports of shared-composables to verify zero compile-time breakage after rename. Will be activated only if type-check fails after the rename pass.
  status: not-needed

## Approved Expansions
-
