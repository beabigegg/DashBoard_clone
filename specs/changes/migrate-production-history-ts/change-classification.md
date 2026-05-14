# Change Classification

## Change Types
- primary: refactor (TypeScript migration)
- secondary: tech-debt

## Risk Level
- low

## Impact Radius
- module-level

## Tier
- 3

## Tier Justification
This is a Phase 3 per-app TypeScript migration with strictly zero behavior change — no backend, SQL, API, cache, spool, or DuckDB runtime is touched. Per CLAUDE.md's TypeScript Migration Rules, prior Phase 3 migrations of comparable scope (reject-history, hold-history, qc-gate, resource-status) were classified Tier 3, and production-history has equivalent surface area (one main entry, one App.vue, one composable, two component SFCs). All shared dependencies the app imports (`shared-ui`, `shared-composables`, `core/api`) are already TypeScript, so no cross-phase `@ts-expect-error` shims should be required.

Tier 3 (not lower) is appropriate because production-history has high runtime criticality (Oracle → spool → DuckDB three-tier path) and is exercised by Python parity/safety tests, Vitest tests, abort tests, legacy node tests, validation tests, and an E2E. The CLAUDE.md TS Migration Rules call out specific failure modes (parity test `.js` paths, Vitest `require()` vs `import`, paired `node --test` regex assertions, partial barrels, stale `.js` import specifiers in SFCs) that all need audit — non-trivial but mechanical.

## Architecture Review Required
- no
- reason: (n/a)

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | TS migration; current behavior is the contract — no need to re-document |
| proposal.md | no | mechanical migration; no proposal needed |
| spec.md | no | rules already in CLAUDE.md TS Migration Rules |
| design.md | no | no architectural design changes |
| qa-report.md | yes | release-readiness sign-off required for module touching critical runtime path |
| regression-report.md | no | covered by existing parity/safety/abort/validation tests |

## Required Contracts
- API: (none — no API surface change)
- CSS/UI: contracts/css/css-contract.md (verify no impact — SFC `<style>` blocks unchanged)
- Env: (none)
- Data shape: (none)
- Business logic: (none)
- CI/CD: contracts/ci/ci-gate-contract.md (verify gates remain green; no contract change expected)

## Required Tests
- unit: existing useProductionHistory.validation.test.js coverage retained; no new unit tests
- contract: not applicable
- integration: existing parity tests retained; no new integration tests
- E2E: existing tests/e2e/test_production_history_e2e.py provides regression coverage
- visual: not applicable (no UI design change)
- data-boundary: not applicable
- resilience: existing abort test retained
- fuzz/monkey: not applicable
- stress: not applicable
- soak: not applicable

## Required Agents
1. frontend-engineer — perform .js → .ts migration, audit downstream tests
2. ci-cd-gatekeeper — run type-check, build, vitest, pytest; verify all gates green
3. qa-reviewer — release-readiness sign-off; smoke verification of production-history page behavior

## Inferred Acceptance Criteria
- AC-1: `cd frontend && npm run type-check` passes with zero errors for all files under `frontend/src/production-history/`
- AC-2: `cd frontend && npm run build` succeeds and bundles `production-history` entry (Vite resolves `main.ts` from `index.html`'s `./main.js` reference)
- AC-3: `cd frontend && npm run test` (Vitest) passes — including any abort/validation/legacy tests touching production-history
- AC-4: `pytest` passes — all `tests/test_*_parity.py` and `tests/test_*_safety.py` referencing production-history resolve to the new `.ts` paths
- AC-5: Browser smoke test — open production-history page, execute a query, verify ProductionMatrix and ProductionDetailTable render with correct data and no console errors
- AC-6: `frontend/src/production-history/index.html` is NOT modified (per CLAUDE.md rule that Vite auto-resolves `main.ts` from `./main.js` reference)
- AC-7: No regression to abort behavior — `frontend/tests/abort/production-history-abort.test.js` passes (after conversion from `require()` to static `import` if needed)
- AC-8: `cd frontend && npm run css:check` still passes (no CSS contract impact)

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5

## Clarifications or Assumptions
- Assumption: production-history does not use echarts (verified — no chart components in the directory). If echarts is encountered during implementation, follow CLAUDE.md's "echarts callback TODO" pattern.
- Assumption: `index.html` references `./main.js` and Vite auto-resolves `main.ts` (per CLAUDE.md pattern, do not modify).
- Assumption: All Python parity/safety tests that reference `production-history` source files must be audited and updated for `.ts` extension (per CLAUDE.md audit rule).

## Context Manifest Draft

### Affected Surfaces
- frontend/src/production-history/main.js → main.ts
- frontend/src/production-history/App.vue (lang="ts")
- frontend/src/production-history/composables/useProductionHistory.js → .ts
- frontend/src/production-history/components/ProductionMatrix.vue (lang="ts")
- frontend/src/production-history/components/ProductionDetailTable.vue (lang="ts")
- frontend/tests/abort/production-history-abort.test.js (audit for require()/imports)
- frontend/tests/legacy/production-history.test.js (audit for readSource regex + .js paths)
- frontend/tests/validation/useProductionHistory.validation.test.js (audit for .js imports)
- tests/test_*_parity.py (audit for production-history .js paths)
- tests/test_*_safety.py (audit for production-history .js paths)
- frontend/src/production-history/index.html (verify NOT modified)

### Allowed Paths
- specs/changes/migrate-production-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- CLAUDE.md
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/abort/
- frontend/tests/legacy/
- frontend/tests/validation/
- frontend/tests/components/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- frontend/package.json
- tests/
- contracts/ci/
- contracts/css/

### Agent Work Packets

#### change-classifier
- specs/changes/migrate-production-history-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- CLAUDE.md

#### frontend-engineer
- specs/changes/migrate-production-history-ts/
- CLAUDE.md
- frontend/src/production-history/
- frontend/src/shared-ui/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tests/abort/
- frontend/tests/legacy/
- frontend/tests/validation/
- frontend/tests/components/
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/vitest.config.js
- tests/

#### ci-cd-gatekeeper
- specs/changes/migrate-production-history-ts/
- contracts/ci/
- frontend/package.json
- frontend/tsconfig.json

#### qa-reviewer
- specs/changes/migrate-production-history-ts/
- frontend/src/production-history/
- tests/
