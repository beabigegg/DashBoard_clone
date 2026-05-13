# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/hold-detail/

## Allowed Paths
- specs/changes/migrate-wip-hold-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/src/resource-shared/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- frontend/scripts/
- frontend/tests/
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

## Required Contracts
- contracts/ci/ci-gate-contract.md (read-only — confirm existing gates cover migrated surface)
- contracts/css/css-contract.md (read-only — confirm no token/class drift)
- contracts/css/css-inventory.md (read-only — confirm no authored-CSS file changes)

## Required Tests
- frontend/tests/ (Vitest suite — npm run test)
- vue-tsc type check (npm run type-check)
- CSS governance (npm run css:check)
- Python parity audit: tests/test_frontend_compute_parity.py and tests/test_frontend_duckdb_parity.py (grep only — no stale .js refs in migrated apps)

## Agent Work Packets

### contract-reviewer
- specs/changes/migrate-wip-hold-ts/
- specs/context/contracts-index.md
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

### frontend-engineer
- specs/changes/migrate-wip-hold-ts/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/wip-shared/
- frontend/src/resource-shared/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/package.json
- frontend/tests/

### ci-cd-gatekeeper
- specs/changes/migrate-wip-hold-ts/
- contracts/ci/ci-gate-contract.md
- frontend/package.json
- frontend/tsconfig.json
- frontend/vitest.config.js
- frontend/scripts/

### qa-reviewer
- specs/changes/migrate-wip-hold-ts/
- frontend/src/wip-overview/
- frontend/src/wip-detail/
- frontend/src/hold-overview/
- frontend/src/hold-detail/
- frontend/tests/

## Context Expansion Requests
-

## Approved Expansions
-
