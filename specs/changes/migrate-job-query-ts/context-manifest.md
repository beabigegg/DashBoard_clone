# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- `frontend/src/job-query/main.js` → `main.ts` (rename + type annotations)
- `frontend/src/job-query/composables/useJobQueryData.js` → `useJobQueryData.ts` (rename + typed return interface)
- `frontend/src/job-query/App.vue` (add `lang="ts"`, drop `.js` specifier, typed props/functions)
- `frontend/tsconfig.json` (add `"src/job-query/**/*"` to `include` array)
- `contracts/ci/ci-gate-contract.md` (schema-version 1.3.10 → 1.3.11 + scope expansion note)
- `contracts/CHANGELOG.md` (new entry [ci 1.3.11])

## Allowed Paths
- specs/changes/migrate-job-query-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/job-query/
- frontend/src/core/
- frontend/src/shared-ui/
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tests/legacy/portal-shell-parity-table-chart-matrix.test.js

## Required Contracts
- contracts/ci/ci-gate-contract.md

## Required Tests
- frontend/tests/legacy/portal-shell-parity-table-chart-matrix.test.js
- existing Vitest unit suite (npm run test)
- npm run type-check
- npm run css:check

## Agent Work Packets

### change-classifier
- specs/changes/migrate-job-query-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-job-query-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### test-strategist
- specs/changes/migrate-job-query-ts/
- frontend/src/job-query/
- frontend/tests/legacy/portal-shell-parity-table-chart-matrix.test.js

### frontend-engineer
- specs/changes/migrate-job-query-ts/
- frontend/src/job-query/
- frontend/src/core/
- frontend/src/shared-ui/
- frontend/tsconfig.json

### ci-cd-gatekeeper
- specs/changes/migrate-job-query-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### qa-reviewer
- specs/changes/migrate-job-query-ts/

## Context Expansion Requests
-

## Approved Expansions
-
