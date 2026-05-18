# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend feature app: `material-trace`

## Allowed Paths
- specs/changes/migrate-material-trace-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/material-trace/
- frontend/src/core/api.ts
- frontend/src/core/reject-history-filters.ts
- frontend/tests/legacy/material-trace-composables.test.js
- frontend/tests/validation/useMaterialTrace.validation.test.js
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- contracts/

## Required Contracts
- none

## Required Tests
- frontend/tests/legacy/material-trace-composables.test.js
- frontend/tests/validation/useMaterialTrace.validation.test.js

## Agent Work Packets

### contract-reviewer
- specs/changes/migrate-material-trace-ts/
- specs/context/contracts-index.md
- contracts/

### test-strategist
- specs/changes/migrate-material-trace-ts/
- frontend/tests/legacy/material-trace-composables.test.js
- frontend/tests/validation/useMaterialTrace.validation.test.js
- frontend/vitest.config.js
- frontend/package.json

### ci-cd-gatekeeper
- specs/changes/migrate-material-trace-ts/
- frontend/package.json
- frontend/tsconfig.json

### implementation-planner
- specs/changes/migrate-material-trace-ts/
- frontend/src/material-trace/
- frontend/src/core/api.ts
- frontend/src/core/reject-history-filters.ts
- frontend/tsconfig.json
- frontend/vite.config.ts

### frontend-engineer
- specs/changes/migrate-material-trace-ts/
- frontend/src/material-trace/
- frontend/src/core/api.ts
- frontend/src/core/reject-history-filters.ts
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js

### qa-reviewer
- specs/changes/migrate-material-trace-ts/

## Context Expansion Requests
-

## Approved Expansions
-
