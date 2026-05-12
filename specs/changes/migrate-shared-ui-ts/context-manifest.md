# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- `frontend/src/shared-ui/components/` — 22 Vue SFCs (add `lang="ts"`, convert to `defineProps<T>()`)
- `frontend/src/shared-ui/index.js` → renamed to `index.ts`
- `frontend/tsconfig.json` — add `"src/shared-ui/**/*"` to `include`

## Allowed Paths
- specs/changes/migrate-shared-ui-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- specs/archive/2026/migrate-core-to-typescript/
- specs/archive/2026/migrate-shared-composables-ts/
- frontend/src/shared-ui/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/tsconfig.json
- frontend/package.json
- frontend/vite.config.ts
- frontend/tests/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

## Required Contracts
- `contracts/ci/ci-gate-contract.md` — verify-only; `npm run type-check` must remain passing
- `contracts/css/css-contract.md` — verify-only; no `@layer` or token edits in shared-ui
- `contracts/css/css-inventory.md` — verify-only; shared-ui inventory entries unchanged

## Required Tests
- `cd frontend && npm run type-check` (AC-5) — primary success gate
- `cd frontend && npm run build` (AC-6) — barrel-import regression catch
- `cd frontend && npm run test` (AC-7) — Vitest; audit for `require()` consumers of renamed files
- `cd frontend && npm run css:check` — CSS governance
- `pytest tests/test_frontend_compute_parity.py tests/test_frontend_duckdb_parity.py` (AC-8)

## Agent Work Packets

### contract-reviewer
- specs/changes/migrate-shared-ui-ts/
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

### test-strategist
- specs/changes/migrate-shared-ui-ts/
- frontend/src/shared-ui/
- frontend/tests/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- specs/archive/2026/migrate-shared-composables-ts/

### frontend-engineer
- specs/changes/migrate-shared-ui-ts/
- frontend/src/shared-ui/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/tsconfig.json
- frontend/package.json
- frontend/vite.config.ts
- frontend/tests/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- specs/archive/2026/migrate-shared-composables-ts/

### ci-cd-gatekeeper
- specs/changes/migrate-shared-ui-ts/
- frontend/tsconfig.json
- frontend/package.json
- contracts/ci/ci-gate-contract.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

### qa-reviewer
- specs/changes/migrate-shared-ui-ts/
- frontend/src/shared-ui/
- frontend/tsconfig.json

## Context Expansion Requests
-

## Approved Expansions
-
