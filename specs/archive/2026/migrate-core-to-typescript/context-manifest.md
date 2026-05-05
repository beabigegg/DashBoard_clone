# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/core/ (21 .js files + existing index.ts placeholder)
- frontend/tsconfig.json (include scope expansion from src/core/index.ts to src/core/**)
- frontend/tests/core/, frontend/tests/schema-guard.test.js, frontend/tests/unwrap-api-result.test.js, frontend/tests/legacy/* (test imports may need extension fixups; tests stay .js)
- ts-migration-plan.md (project-root reference, read-only)

## Allowed Paths
- specs/changes/migrate-core-to-typescript/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/core/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/package.json
- frontend/vitest.config.js
- frontend/tests/core/
- frontend/tests/schema-guard.test.js
- frontend/tests/unwrap-api-result.test.js
- frontend/tests/legacy/
- frontend/tests/pending-jobs-registry.test.js
- ts-migration-plan.md
- contracts/ci/ci-gate-contract.md
- contracts/api/api-contract.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

## Required Contracts
- none (read-only references only: contracts/api/api-contract.md, contracts/ci/ci-gate-contract.md)

## Required Tests
- frontend/tests/core/api-dedup.test.js
- frontend/tests/schema-guard.test.js
- frontend/tests/unwrap-api-result.test.js
- frontend/tests/legacy/datetime.test.js
- frontend/tests/legacy/autocomplete.test.js
- frontend/tests/legacy/wip-derive.test.js
- frontend/tests/legacy/shell-navigation.test.js
- frontend/tests/pending-jobs-registry.test.js

## Agent Work Packets

### change-classifier
- specs/changes/migrate-core-to-typescript/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-core-to-typescript/
- contracts/api/api-contract.md
- contracts/ci/ci-gate-contract.md
- frontend/src/core/
- frontend/tsconfig.json

### test-strategist
- specs/changes/migrate-core-to-typescript/
- frontend/tests/core/
- frontend/tests/schema-guard.test.js
- frontend/tests/unwrap-api-result.test.js
- frontend/tests/legacy/
- frontend/tests/pending-jobs-registry.test.js
- frontend/package.json
- frontend/tsconfig.json

### frontend-engineer
- specs/changes/migrate-core-to-typescript/
- frontend/src/core/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/package.json
- frontend/vitest.config.js
- frontend/tests/core/
- frontend/tests/schema-guard.test.js
- frontend/tests/unwrap-api-result.test.js
- frontend/tests/legacy/
- frontend/tests/pending-jobs-registry.test.js
- ts-migration-plan.md

### ci-cd-gatekeeper
- specs/changes/migrate-core-to-typescript/
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml
- frontend/package.json
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md

### qa-reviewer
- specs/changes/migrate-core-to-typescript/
- frontend/src/core/
- frontend/tsconfig.json
- frontend/package.json
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

## Context Expansion Requests
-

## Approved Expansions
-
