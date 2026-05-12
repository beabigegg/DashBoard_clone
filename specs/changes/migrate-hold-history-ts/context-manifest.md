# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/hold-history/ (migration target — all 14 files)
- frontend/tsconfig.json (include array expansion)
- contracts/ci/ci-gate-contract.md (schema-version bump 1.3.5 → 1.3.6 + Gate Compatibility Note)
- contracts/CHANGELOG.md (new entry [ci 1.3.6])

## Allowed Paths
- specs/changes/migrate-hold-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/hold-history/
- frontend/src/reject-history/
- frontend/src/shared-composables/
- frontend/src/wip-shared/
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

## Required Contracts
- contracts/ci/ci-gate-contract.md

## Required Tests
- frontend/tests/ (Vitest suite — 270+ tests must pass)

## Agent Work Packets

### change-classifier
- specs/changes/migrate-hold-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-hold-history-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### test-strategist
- specs/changes/migrate-hold-history-ts/
- frontend/src/hold-history/

### frontend-engineer
- specs/changes/migrate-hold-history-ts/
- frontend/src/hold-history/
- frontend/src/shared-composables/
- frontend/src/wip-shared/
- frontend/src/reject-history/
- frontend/tsconfig.json

### ci-cd-gatekeeper
- specs/changes/migrate-hold-history-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### qa-reviewer
- specs/changes/migrate-hold-history-ts/

## Context Expansion Requests
-

## Approved Expansions
-
