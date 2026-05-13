# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/qc-gate/ (migration target — 5 files: main.js, App.vue, composables/useQcGateData.js, components/LotTable.vue, components/QcGateChart.vue)
- frontend/tsconfig.json (include array expansion)
- contracts/ci/ci-gate-contract.md (schema-version bump 1.3.7 → 1.3.8 + Gate Compatibility Note)
- contracts/CHANGELOG.md (new entry [ci 1.3.8])

## Allowed Paths
- specs/changes/migrate-qc-gate-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/qc-gate/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

## Required Contracts
- contracts/ci/ci-gate-contract.md — schema-version bump 1.3.7 → 1.3.8; CHANGELOG.md entry [ci 1.3.8] documenting Phase 3 item #17 scope expansion

## Required Tests
- Existing Vitest suites covering qc-gate/ must pass after migration
- npm run type-check must pass with zero errors (src/qc-gate/**/* now included)
- npm run build smoke — confirms Vite resolves main.ts from index.html's ./main.js reference
- npm run css:check must pass with zero violations

## Agent Work Packets

### change-classifier
- specs/changes/migrate-qc-gate-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-qc-gate-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- frontend/tsconfig.json

### test-strategist
- specs/changes/migrate-qc-gate-ts/
- frontend/src/qc-gate/

### frontend-engineer
- specs/changes/migrate-qc-gate-ts/
- frontend/src/qc-gate/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/tsconfig.json

### ci-cd-gatekeeper
- specs/changes/migrate-qc-gate-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### qa-reviewer
- specs/changes/migrate-qc-gate-ts/
- frontend/src/qc-gate/

## Context Expansion Requests
-

## Approved Expansions
-
