# Change Classification

## Change Types
- primary: typescript-migration
- secondary: frontend-refactor

## Risk Level
- low

## Impact Radius
- cross-module (shared-ui is consumed by every feature SPA and portal-shell)

## Tier
- 2

## Architecture Review Required
- no

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | mechanical migration — no behavior under investigation |
| proposal.md | no | scope predetermined by ts-migration-plan.md |
| spec.md | no | mechanical migration with explicit success criterion |
| design.md | no | no design decisions |
| qa-report.md | yes | 12 acceptance criteria require explicit per-AC pass/fail record |
| regression-report.md | no | |

## Required Contracts
- API: none — no API change
- CSS/UI: verify-only (no edits) — `contracts/css/css-contract.md`, `contracts/css/css-inventory.md`
- Env: none
- Data shape: none
- Business logic: none
- CI/CD: verify-only (no edits) — `contracts/ci/ci-gate-contract.md`

## Required Tests
- unit: `npm run type-check` (vue-tsc --noEmit), `npm run build`
- contract: n/a
- integration: `npm run test` (Vitest), `pytest tests/test_frontend_*_parity.py`
- E2E: n/a (existing coverage sufficient)
- visual: n/a (constraint: no visual change)
- data-boundary: n/a
- resilience: n/a
- fuzz/monkey: n/a
- stress: n/a
- soak: n/a

## Required Agents
1. contract-reviewer
2. test-strategist
3. frontend-engineer
4. ci-cd-gatekeeper
5. qa-reviewer

## Inferred Acceptance Criteria
- AC-1: All 22 Vue SFCs in `frontend/src/shared-ui/components/` use `<script setup lang="ts">` with no remaining untyped `<script setup>` blocks.
- AC-2: All props declarations use `defineProps<T>()` generic syntax (TypeScript-native), not the runtime object form.
- AC-3: `frontend/src/shared-ui/index.js` is renamed to `index.ts` and re-exports all 22 components with no broken imports.
- AC-4: `frontend/tsconfig.json` `include` array contains `"src/shared-ui/**/*"` in addition to existing core/ and shared-composables/ entries.
- AC-5: `cd frontend && npm run type-check` (vue-tsc --noEmit) exits 0 with 0 errors attributable to shared-ui.
- AC-6: `cd frontend && npm run build` succeeds end-to-end (catches barrel-import regressions Vite-side).
- AC-7: `cd frontend && npm run test` (Vitest) passes — no test file broken by the `.js → .ts` rename.
- AC-8: `pytest tests/test_frontend_*_parity.py` passes — no Python parity test references a renamed shared-ui `.js` path.
- AC-9: No `@ts-ignore` introduced; every `@ts-expect-error` carries a comment referencing the pending migration phase.
- AC-10: Every `any` type carries a `// TODO: type <description>` comment.
- AC-11: No `<template>` or `<style>` blocks modified; no CSS or Tailwind config changes.
- AC-12: No runtime behavior change — components emit the same events, accept the same props by name and shape.

## Tasks Not Applicable
- 2.1 (no API contract change)
- 2.2 (CSS contract: verify-only, no edit)
- 2.3 (no env contract change)
- 2.4 (no data shape contract change)
- 2.5 (no business logic contract change)
- 2.6 (CI/CD contract: verify-only, no edit)
- 3.3 (no E2E/resilience tests — mechanical migration)
- 3.4 (no monkey tests)
- 3.5 (no stress/soak tests)
- 4.1 (no backend changes)
- 4.3 (no env/deploy changes)
- 5.1 (no UI/UX review — constraint: no visual change)
- 5.2 (no visual review)
- 6.4 (no nightly/weekly/manual gates required)

## Clarifications or Assumptions
- Phase 1a (core/) and Phase 1b (shared-composables/) types are available for import without `@ts-expect-error`.
- Components that import from not-yet-migrated feature `.js` files must use the declared-interface + `@ts-expect-error` + cast pattern established in Phase 1b.
- `index.js → index.ts` rename is handled by Vite's module resolver at runtime; Vitest and Python parity tests must be audited for hardcoded `.js` paths (Phase 1a/1b lessons).

## Context Manifest Draft

### Affected Surfaces
- `frontend/src/shared-ui/components/` — 22 Vue SFCs
- `frontend/src/shared-ui/index.js` → renamed to `index.ts`
- `frontend/tsconfig.json` — add `src/shared-ui/**/*` to `include`

### Allowed Paths
- specs/changes/migrate-shared-ui-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- specs/archive/2026/migrate-core-to-typescript/
- specs/archive/2026/migrate-shared-composables-ts/
- frontend/src/shared-ui/**
- frontend/src/core/**/*.ts
- frontend/src/shared-composables/**/*.ts
- frontend/tsconfig.json
- frontend/package.json
- frontend/vite.config.*
- frontend/tests/**
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

### Agent Work Packets

#### contract-reviewer
- specs/changes/migrate-shared-ui-ts/
- contracts/ci/ci-gate-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

#### test-strategist
- specs/changes/migrate-shared-ui-ts/
- frontend/src/shared-ui/**
- frontend/tests/**
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- specs/archive/2026/migrate-shared-composables-ts/

#### frontend-engineer
- specs/changes/migrate-shared-ui-ts/
- frontend/src/shared-ui/**
- frontend/src/core/**/*.ts
- frontend/src/shared-composables/**/*.ts
- frontend/tsconfig.json
- frontend/package.json
- frontend/vite.config.*
- frontend/tests/**
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- specs/archive/2026/migrate-shared-composables-ts/

#### ci-cd-gatekeeper
- specs/changes/migrate-shared-ui-ts/
- frontend/tsconfig.json
- frontend/package.json
- contracts/ci/ci-gate-contract.md
- .github/workflows/frontend-tests.yml
- .github/workflows/contract-driven-gates.yml

#### qa-reviewer
- specs/changes/migrate-shared-ui-ts/
- frontend/src/shared-ui/**
- frontend/tsconfig.json
