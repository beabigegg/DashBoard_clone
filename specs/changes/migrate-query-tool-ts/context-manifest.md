# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- frontend/src/query-tool/ (all .js files, all .vue SFCs)
- frontend/tests/legacy/query-tool-composables.test.js
- frontend/tests/query-tool/
- frontend/tests/abort/query-tool-abort.test.js
- frontend/tests/playwright/query-tool.spec.js
- frontend/tests/playwright/query-tool-url-state.spec.js
- tests/ (Python — audit for hardcoded .js paths referencing query-tool)

## Allowed Paths
- specs/changes/migrate-query-tool-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/query-tool/
- frontend/tests/legacy/
- frontend/tests/query-tool/
- frontend/tests/abort/
- frontend/tests/playwright/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- tests/

## Required Contracts
- none

## Required Tests
- frontend/tests/legacy/query-tool-composables.test.js (must stay green)
- frontend/tests/query-tool/ (all tests must stay green)
- frontend/tests/abort/query-tool-abort.test.js (must stay green)
- frontend/tests/playwright/query-tool.spec.js (informational — E2E, nightly)
- frontend/tests/playwright/query-tool-url-state.spec.js (informational — E2E, nightly)
- tests/ Python suite — assert no broken .js path references after rename

## Agent Work Packets

### change-classifier
- specs/changes/migrate-query-tool-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### frontend-engineer
- specs/changes/migrate-query-tool-ts/
- frontend/src/query-tool/
- frontend/tests/legacy/
- frontend/tests/query-tool/
- frontend/tests/abort/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- tests/

### qa-reviewer
- specs/changes/migrate-query-tool-ts/
- frontend/src/query-tool/
- frontend/tests/legacy/
- frontend/tests/query-tool/
- frontend/tests/abort/
- frontend/tests/playwright/

## Context Expansion Requests
-

## Approved Expansions
-
