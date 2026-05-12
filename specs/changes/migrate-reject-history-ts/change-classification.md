# Change Classification

## Change Types
- primary: TypeScript migration (pure refactor)
- secondary: CI gate scope expansion

## Risk Level
- low

## Impact Radius
- module-level (reject-history/ only; shared layers already migrated)

## Tier
- 3

## Architecture Review Required
- no

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | no behavior change; existing tests document current behavior |
| proposal.md | no | change-request.md is sufficient |
| spec.md | no | migration rules fully captured in CLAUDE.md |
| design.md | no | no new architecture; DuckDB typing patterns established by migration itself |
| qa-report.md | yes | summarizes type-check pass, Vitest counts, Playwright regression, TODO:type debt |
| regression-report.md | no | Tier 3; existing CI gates are sufficient regression evidence |

## Required Contracts
- API: none
- CSS/UI: none
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: contracts/ci/ci-gate-contract.md — expand frontend-type-check scope to include src/reject-history/**/*; bump schema-version to 1.3.5

## Required Tests
- unit: frontend/tests/components/ParetoGrid.test.js, frontend/tests/validation/useRejectHistory.validation.test.js
- contract: none (pure TS migration)
- integration: tests/test_frontend_compute_parity.py (audit), tests/test_frontend_duckdb_parity.py (audit)
- E2E: frontend/tests/playwright/reject-history.spec.js (regression check)
- visual: none
- data-boundary: frontend/tests/legacy/reject-history-date-range-limit.test.js
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- contract-reviewer
- test-strategist
- frontend-engineer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: `npm run type-check` passes with zero errors in reject-history/ scope (strict: true, all migrated .vue and .ts files covered by tsconfig.json include)
- AC-2: All pre-existing Vitest tests continue to pass (frontend/tests/abort/reject-history-abort.test.js, frontend/tests/components/ParetoGrid.test.js, frontend/tests/legacy/reject-history-date-range-limit.test.js, frontend/tests/validation/useRejectHistory.validation.test.js)
- AC-3: No runtime behavior changes — Pareto grid, multi-dimension filtering, DuckDB queries, and abort behavior remain identical
- AC-4: Every `any` usage annotated with `// TODO: type <reason>`; no bare `any` or `@ts-ignore`
- AC-5: All .js extension specifiers inside migrated SFCs are dropped to bare specifiers (TypeScript/Vite auto-resolution)
- AC-6: Python parity tests (tests/test_frontend_*_parity.py) pass — any hardcoded .js paths referencing renamed files updated to .ts
- AC-7: contracts/ci/ci-gate-contract.md updated with Phase 3 frontend-type-check scope expansion note and schema-version bumped to 1.3.5

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.3, 2.4, 2.5, 3.3, 3.4, 3.5, 4.1, 4.3, 5.1, 5.2

## Clarifications or Assumptions
- App.vue at 1370 lines is the largest single file migrated to date; annotation effort is high but behavioral risk remains Tier 3.
- useRejectHistoryDuckDB.js (466 lines) introduces novel DuckDB composable typing patterns; these will become reference patterns for hold-history/ and resource-history/.
- All shared layers (Phase 1a–1f) are already TypeScript; no @ts-expect-error stubs needed for cross-boundary imports.

## Context Manifest Draft

### Affected Surfaces
- frontend/src/reject-history/App.vue
- frontend/src/reject-history/main.js → main.ts
- frontend/src/reject-history/useRejectHistoryDuckDB.js → useRejectHistoryDuckDB.ts
- frontend/src/reject-history/components/DetailTable.vue
- frontend/src/reject-history/components/FilterPanel.vue
- frontend/src/reject-history/components/ParetoGrid.vue
- frontend/src/reject-history/components/ParetoSection.vue
- frontend/src/reject-history/components/SummaryCards.vue
- frontend/src/reject-history/components/TrendChart.vue
- frontend/tsconfig.json (add src/reject-history/**/* to include)
- contracts/ci/ci-gate-contract.md (scope expansion note + schema-version bump to 1.3.5)
- tests/test_frontend_compute_parity.py (audit for .js path references)
- tests/test_frontend_duckdb_parity.py (audit for .js path references)

### Allowed Paths
- specs/changes/migrate-reject-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/reject-history/
- frontend/src/reject-history/components/
- frontend/src/core/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/admin-shared/
- frontend/src/resource-shared/
- frontend/src/wip-shared/
- frontend/tests/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/package.json
- contracts/ci/
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- CLAUDE.md
- ts-migration-plan.md

### Agent Work Packets
(see context-manifest.md for per-agent breakdown)

### Required Contracts
- contracts/ci/ci-gate-contract.md

### Required Tests
- frontend/tests/abort/reject-history-abort.test.js
- frontend/tests/components/ParetoGrid.test.js
- frontend/tests/legacy/reject-history-date-range-limit.test.js
- frontend/tests/validation/useRejectHistory.validation.test.js
- frontend/tests/playwright/reject-history.spec.js
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py

### Context Expansion Requests
(none)
