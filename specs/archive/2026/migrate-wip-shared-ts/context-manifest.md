# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/wip-shared/ (migration target: constants.js, composables/useAutocomplete.js, composables/useAutoRefresh.js, components/HoldLotTable.vue, components/Pagination.vue, components/ParetoSection.vue, new index.ts)
- frontend/src/shared-composables/ (@ts-expect-error removal + specifier fixes in useAutocomplete.ts, useAutoRefresh.ts)
- frontend/src/shared-ui/components/PaginationControl.vue (@ts-expect-error removal)
- frontend/src/hold-detail/App.vue (stale .js specifier fix)
- frontend/tsconfig.json (include array expansion)
- contracts/ci/ci-gate-contract.md (schema-version bump to 1.3.4 + Gate Compatibility Note)
- contracts/CHANGELOG.md (new entry [ci 1.3.4])

## Allowed Paths
- specs/changes/migrate-wip-shared-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/wip-shared/
- frontend/src/shared-composables/
- frontend/src/shared-ui/components/PaginationControl.vue
- frontend/src/hold-detail/App.vue
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- specs/archive/2026/migrate-admin-shared-ts/

## Required Contracts
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

## Required Tests
- (existing coverage only — no new test files needed)

## Agent Work Packets

### change-classifier
- specs/changes/migrate-wip-shared-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-wip-shared-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### test-strategist
- specs/changes/migrate-wip-shared-ts/
- frontend/src/wip-shared/

### frontend-engineer
- specs/changes/migrate-wip-shared-ts/
- frontend/src/wip-shared/
- frontend/src/shared-composables/
- frontend/src/shared-ui/components/PaginationControl.vue
- frontend/src/hold-detail/App.vue
- frontend/tsconfig.json

### ci-cd-gatekeeper
- specs/changes/migrate-wip-shared-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### qa-reviewer
- specs/changes/migrate-wip-shared-ts/

## Context Expansion Requests
-

## Approved Expansions
-
