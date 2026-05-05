# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend build toolchain (Vite + TypeScript compiler)
- CI workflow (frontend-tests)
- CI gate contract registry

## Allowed Paths
- specs/changes/add-ts-toolchain/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/package.json
- frontend/package-lock.json
- frontend/vite.config.js
- frontend/vite.config.ts
- frontend/tsconfig.json
- frontend/src/core/
- .github/workflows/frontend-tests.yml
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

## Required Contracts
- contracts/ci/ci-gate-contract.md

## Required Tests
- (none new) — existing Vitest suite must continue to pass; `cdd-kit validate` after contract update

## Agent Work Packets

### change-classifier
- specs/changes/add-ts-toolchain/
- specs/context/project-map.md
- specs/context/contracts-index.md

### test-strategist
- specs/changes/add-ts-toolchain/
- frontend/package.json
- frontend/tsconfig.json
- .github/workflows/frontend-tests.yml
- contracts/ci/ci-gate-contract.md

### frontend-engineer
- specs/changes/add-ts-toolchain/
- frontend/package.json
- frontend/package-lock.json
- frontend/vite.config.js
- frontend/vite.config.ts
- frontend/tsconfig.json
- frontend/src/core/
- contracts/ci/ci-gate-contract.md

### dependency-security-reviewer
- specs/changes/add-ts-toolchain/
- frontend/package.json
- frontend/package-lock.json

### contract-reviewer
- specs/changes/add-ts-toolchain/
- contracts/ci/ci-gate-contract.md
- frontend/package.json
- frontend/tsconfig.json

### ci-cd-gatekeeper
- specs/changes/add-ts-toolchain/
- .github/workflows/frontend-tests.yml
- frontend/package.json
- contracts/ci/ci-gate-contract.md

### qa-reviewer
- specs/changes/add-ts-toolchain/
- frontend/package.json
- frontend/tsconfig.json
- frontend/vite.config.ts
- .github/workflows/frontend-tests.yml
- contracts/ci/ci-gate-contract.md

## Context Expansion Requests
-

## Approved Expansions
-
