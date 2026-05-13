# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- `frontend/src/resource-history/` (migration target — 10 files)
- `frontend/tsconfig.json` (include array expansion — item #15)
- `contracts/ci/ci-gate-contract.md` (schema-version bump 1.3.8 → 1.3.9)
- `contracts/CHANGELOG.md` (new entry [ci 1.3.9])

## Allowed Paths
- specs/changes/migrate-resource-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/resource-history/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/resource-shared/
- frontend/tests/legacy/resource-history.test.js
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

## Required Contracts
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md

## Required Tests
- frontend/tests/legacy/resource-history.test.js (read-only guard — no changes needed)
- `npm run type-check` (zero errors with src/resource-history/**/* in tsconfig)
- `npm run test` (full Vitest suite — zero regressions)
- `npm run css:check` (zero violations)
- `npm run build` (clean build)

## Agent Work Packets

### change-classifier
- specs/changes/migrate-resource-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-resource-history-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### test-strategist
- specs/changes/migrate-resource-history-ts/
- frontend/src/resource-history/
- frontend/tests/legacy/resource-history.test.js

### frontend-engineer
- specs/changes/migrate-resource-history-ts/
- frontend/src/resource-history/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/resource-shared/
- frontend/tests/legacy/resource-history.test.js
- frontend/tsconfig.json

### ci-cd-gatekeeper
- specs/changes/migrate-resource-history-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### qa-reviewer
- specs/changes/migrate-resource-history-ts/
- frontend/src/resource-history/

## Context Expansion Requests
-

## Approved Expansions
-
