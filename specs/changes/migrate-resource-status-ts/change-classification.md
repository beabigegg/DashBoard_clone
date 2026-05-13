# Change Classification

## Change Types
- primary: frontend refactor
- secondary: TypeScript migration (Phase 3, item #19)

## Risk Level
- low

## Impact Radius
- isolated

## Tier
- 4

## Architecture Review Required
- no
- reason: follows established Phase 3 migration pattern (same as reject-history, hold-history, wip migrations)

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | behavior preservation implicit; Vitest + smoke check covers it |
| proposal.md | no | already in ts-migration-plan.md item #19 |
| spec.md | no | change-request.md + AC list sufficient |
| design.md | no | no design decisions — follows established Phase 3 playbook |
| qa-report.md | no | |
| regression-report.md | no | |

## Required Contracts
- API: contracts/frontend/ — verify /api/resource/status/options, /api/resource/status/summary, /api/resource/status shapes unchanged
- CSS/UI: none
- Env: none
- Data shape: none (API shape verified read-only by contract-reviewer)
- Business logic: none
- CI/CD: npm run type-check, npm run test, npm run build, npm run css:check must pass

## Required Tests
- unit: existing Vitest suites for resource-status/ must pass unchanged
- contract: npm run type-check zero errors
- integration: not required
- E2E: not required (no behavior change)
- visual: not required
- data-boundary: not required
- resilience: not required
- fuzz/monkey: not required
- stress: not required
- soak: not required

## Required Agents
- contract-reviewer
- test-strategist
- frontend-engineer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: frontend/src/resource-status/main.js renamed to main.ts; all 7 SFCs use <script setup lang="ts"> with typed props, emits, and reactive state.
- AC-2: npm run type-check passes with zero errors; npm run test, npm run css:check, and npm run build remain green; no runtime regression.
- AC-3: All cross-layer .js import specifiers in migrated SFCs are rewritten with extension dropped (not .ts); index.html continues to reference ./main.js unchanged; echarts callback parameters annotated // TODO: type echarts callback where lacking precise types.

## Tasks Not Applicable
- not-applicable: 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2

## Clarifications or Assumptions
- resource-shared/constants.ts and resource-shared/index.ts are already TypeScript — no migration needed there
- FloatingTooltip.vue imports ../../core/api.js — drop extension only, do not rename
- index.html entry ./main.js is intentionally left unchanged (Vite resolves main.ts at build time)

## Context Manifest Draft

### Affected Surfaces
- frontend/src/resource-status/ (all files)

### Allowed Paths
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

### Agent Work Packets

#### change-classifier
- specs/changes/migrate-resource-status-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### contract-reviewer
- specs/changes/migrate-resource-status-ts/
- contracts/frontend/
- frontend/src/resource-status/

#### test-strategist
- specs/changes/migrate-resource-status-ts/
- frontend/src/resource-status/
- frontend/tests/
- frontend/vitest.config.ts

#### frontend-engineer
- specs/changes/migrate-resource-status-ts/
- frontend/src/resource-status/
- frontend/src/resource-shared/
- frontend/src/core/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/tsconfig.json

#### ci-cd-gatekeeper
- specs/changes/migrate-resource-status-ts/
- frontend/package.json
- frontend/tsconfig.json
- frontend/src/resource-status/
- .github/workflows/

#### qa-reviewer
- specs/changes/migrate-resource-status-ts/
- frontend/src/resource-status/
