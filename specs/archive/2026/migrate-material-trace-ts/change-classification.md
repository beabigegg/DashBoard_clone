# Change Classification

## Change Types
- primary: refactor
- secondary: typescript-migration

## Risk Level
- low

## Impact Radius
- module-level (single feature app: `frontend/src/material-trace/`)

## Tier
- 3

## Architecture Review Required
- no
- reason: established Phase 3 per-app migration pattern; no new design decisions

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | no architecture change; pattern already established |
| qa-report.md | no | routine TS migration; agent-log pointer sufficient |
| regression-report.md | no | no behavior change; build + tests + type-check serve as evidence |
| visual-review-report.md | no | no CSS/template change |
| monkey-test-report.md | no | |
| stress-soak-report.md | no | |

## Required Contracts
- API: none (no API surface change)
- CSS/UI: none (no style.css change)
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: none

## Required Tests
- unit: existing material-trace-composables.test.js and useMaterialTrace.validation.test.js must continue to pass
- contract: none
- integration: none
- E2E: existing test_material_trace_e2e.py sanity check (no new E2E required)
- visual: none
- data-boundary: none
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- contract-reviewer
- test-strategist
- ci-cd-gatekeeper
- implementation-planner
- frontend-engineer
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: `frontend/src/material-trace/main.js` is renamed to `main.ts` with no behavior change (same `createApp(App).mount('#app')` semantics).
- AC-2: `frontend/src/material-trace/App.vue` has `<script setup lang="ts">` with appropriate type annotations; no `as any` escapes introduced beyond what established Phase 3 apps tolerate.
- AC-3: Import specifiers inside `App.vue` drop the `.js` extension from already-migrated core imports (`../core/api`, `../core/reject-history-filters`).
- AC-4: `frontend/src/material-trace/index.html` continues to reference `./main.js` (Vite resolves to `main.ts` at build time) — NOT modified.
- AC-5: `cd frontend && npm run type-check` passes with zero new errors attributable to this change.
- AC-6: `cd frontend && npm run build` succeeds and produces the material-trace bundle.
- AC-7: `cd frontend && npm run test` passes — both material-trace test files continue to import successfully.
- AC-8: `cd frontend && npm run css:check` passes (no CSS change expected; sanity).

## Tasks Not Applicable
- not-applicable: 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 4.4, 5.1, 5.2

## Clarifications or Assumptions
- Both `frontend/src/core/api.ts` and `frontend/src/core/reject-history-filters.ts` already exist as `.ts` files (Phase 1 migrated).
- No Python parity or safety test files reference material-trace `.js` source paths.
- `tests/e2e/test_material_trace_e2e.py` is browser-driven and independent of source file extensions; not modified by this change.

## Context Manifest Draft

### Affected Surfaces
- frontend feature app: `material-trace`

### Allowed Paths
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

### Required Contracts
- none

### Required Tests
- frontend/tests/legacy/material-trace-composables.test.js
- frontend/tests/validation/useMaterialTrace.validation.test.js

### Agent Work Packets

#### contract-reviewer
- specs/changes/migrate-material-trace-ts/
- specs/context/contracts-index.md
- contracts/

#### test-strategist
- specs/changes/migrate-material-trace-ts/
- frontend/tests/legacy/material-trace-composables.test.js
- frontend/tests/validation/useMaterialTrace.validation.test.js
- frontend/vitest.config.js
- frontend/package.json

#### ci-cd-gatekeeper
- specs/changes/migrate-material-trace-ts/
- frontend/package.json
- frontend/tsconfig.json

#### implementation-planner
- specs/changes/migrate-material-trace-ts/
- frontend/src/material-trace/
- frontend/src/core/api.ts
- frontend/src/core/reject-history-filters.ts
- frontend/tsconfig.json
- frontend/vite.config.ts

#### frontend-engineer
- specs/changes/migrate-material-trace-ts/
- frontend/src/material-trace/
- frontend/src/core/api.ts
- frontend/src/core/reject-history-filters.ts
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js

#### qa-reviewer
- specs/changes/migrate-material-trace-ts/

### Context Expansion Requests
- (none at classification time)
