---
change-id: migrate-production-history-ts
schema-version: 0.1.0
last-changed: 2026-05-14
risk: low
tier: 3
---

# Test Plan: migrate-production-history-ts

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (type-check) | static analysis | `cd frontend && npm run type-check` (vue-tsc --noEmit) | 3 |
| AC-2 (build) | build | `cd frontend && npm run build` (Vite production bundle) | 3 |
| AC-3 (vitest) | unit/validation | `frontend/tests/validation/useProductionHistory.validation.test.js` | 3 |
| AC-3 (vitest) | abort/resilience | `frontend/tests/abort/production-history-abort.test.js` | 3 |
| AC-3 (vitest) | legacy data-transform | `frontend/tests/legacy/production-history.test.js` | 3 |
| AC-4 (pytest) | route tests | `tests/test_production_history_routes.py` | 3 |
| AC-4 (pytest) | service tests | `tests/test_production_history_service.py` | 3 |
| AC-4 (pytest) | sql runtime tests | `tests/test_production_history_sql_runtime.py` | 3 |
| AC-4 (pytest) | job service tests | `tests/test_production_history_job_service.py` | 3 |
| AC-4 (pytest) | async route tests | `tests/test_production_history_async_routes.py` | 3 |
| AC-5 (smoke) | manual browser | manual: open production-history page, run a query, verify matrix + detail render | 3 |
| AC-6 (index.html) | invariant check | `git diff --stat frontend/src/production-history/index.html` must report 0 changes | 3 |
| AC-7 (abort) | abort/resilience | `frontend/tests/abort/production-history-abort.test.js` (import specifier audit) | 3 |
| AC-8 (css:check) | css governance | `cd frontend && npm run css:check` | 3 |

## Test Families Required

unit (vitest) / integration (pytest existing) / e2e (existing test_production_history_e2e.py; regression only — no new test added)

## Out of Scope

- Adding new unit/integration tests — existing coverage is sufficient for a zero-behavior-change TS migration
- E2E test additions — `tests/e2e/test_production_history_e2e.py` covers the runtime regression surface
- Stress/soak tests — irrelevant for a type-annotation-only change
- Visual regression — no UI change

## Notes

Audit checklist before completion (per CLAUDE.md TS Migration Rules):
1. `frontend/tests/abort/production-history-abort.test.js` line 44, 67, 88, 111 — dynamic `await import('../../src/production-history/composables/useProductionHistory.js')` — drop `.js` extension.
2. `frontend/tests/legacy/production-history.test.js` — no source imports (pure inline); no edits required.
3. `frontend/tests/validation/useProductionHistory.validation.test.js` — does not import production-history sources directly; no edits required.
4. No Python parity/safety test references `production-history` sources; pytest audit confirms zero hits.
5. `frontend/src/production-history/index.html` — leave `./main.js` reference unchanged (Vite resolves `main.ts`).
