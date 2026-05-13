# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/resource-status/ (all files — main.js + 7 SFCs)

## Allowed Paths
- specs/changes/migrate-resource-status-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/resource-status/
- frontend/src/resource-shared/
- frontend/src/core/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/tests/
- frontend/vitest.config.ts
- frontend/tsconfig.json
- frontend/package.json
- contracts/frontend/
- .github/workflows/

## Required Contracts
- contracts/frontend/ — verify /api/resource/status/options, /api/resource/status/summary, /api/resource/status request/response shapes are not impacted (read-only check; no edits expected)

## Required Tests
- Existing Vitest suites covering resource-status/ must still pass after migration
- npm run type-check must pass with zero errors
- npm run build smoke (ensures Vite resolves main.ts from index.html's ./main.js reference)
- Audit frontend/tests/**/*.{js,ts} for any require('.../resource-status/...') calls — convert to static import if found

## Agent Work Packets

### change-classifier
- specs/changes/migrate-resource-status-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-resource-status-ts/
- contracts/frontend/
- frontend/src/resource-status/

### test-strategist
- specs/changes/migrate-resource-status-ts/
- frontend/src/resource-status/
- frontend/tests/
- frontend/vitest.config.ts

### frontend-engineer
- specs/changes/migrate-resource-status-ts/
- frontend/src/resource-status/
- frontend/src/resource-shared/
- frontend/src/core/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/tsconfig.json

### ci-cd-gatekeeper
- specs/changes/migrate-resource-status-ts/
- frontend/package.json
- frontend/tsconfig.json
- frontend/src/resource-status/
- .github/workflows/

### qa-reviewer
- specs/changes/migrate-resource-status-ts/
- frontend/src/resource-status/

## Context Expansion Requests
-

## Approved Expansions
-
