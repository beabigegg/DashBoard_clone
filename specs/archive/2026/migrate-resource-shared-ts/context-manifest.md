# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/resource-shared/ (migration target: constants.js, HierarchyTable.vue, MultiSelect.vue, new index.ts)
- frontend/src/resource-history/components/ (consumer: stale .js specifier fixes)
- frontend/src/resource-status/ (consumer: stale .js specifier fixes)
- frontend/tsconfig.json (include array expansion)
- contracts/ci/ci-gate-contract.md (schema-version bump to 1.3.3 + Gate Compatibility Note)
- contracts/CHANGELOG.md (new entry [ci 1.3.3])

## Allowed Paths
- specs/changes/migrate-resource-shared-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/resource-shared/
- frontend/src/resource-history/components/
- frontend/src/resource-status/
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tests/legacy/resource-status.test.js
- specs/archive/2026/migrate-admin-shared-ts/

## Required Contracts
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

## Required Tests
- frontend/tests/legacy/resource-status.test.js (existing coverage; no changes needed)

## Agent Work Packets

### change-classifier
- specs/changes/migrate-resource-shared-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-resource-shared-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### test-strategist
- specs/changes/migrate-resource-shared-ts/
- frontend/src/resource-shared/
- frontend/tests/legacy/resource-status.test.js

### frontend-engineer
- specs/changes/migrate-resource-shared-ts/
- frontend/src/resource-shared/
- frontend/src/resource-history/components/
- frontend/src/resource-status/
- frontend/tsconfig.json
- frontend/src/core/types.ts

### ci-cd-gatekeeper
- specs/changes/migrate-resource-shared-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### qa-reviewer
- specs/changes/migrate-resource-shared-ts/

## Context Expansion Requests
-

## Approved Expansions
-
