---
change-id: migrate-reject-history-ts
schema-version: 0.1.0
last-changed: 2026-05-12
risk: low
tier: 3
---

# Test Plan: migrate-reject-history-ts

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | static-analysis | `npm run type-check` — zero errors in `src/reject-history/**/*` | static-analysis |
| AC-2 | unit (abort) | `frontend/tests/abort/reject-history-abort.test.js` — all 6 tests | unit |
| AC-2 | unit (component) | `frontend/tests/components/ParetoGrid.test.js` — all 5 tests | unit |
| AC-2 | data-boundary | `frontend/tests/legacy/reject-history-date-range-limit.test.js` — 1 test | unit |
| AC-2 | unit (validation) | `frontend/tests/validation/useRejectHistory.validation.test.js` — all 16 tests | unit |
| AC-3 | E2E | `frontend/tests/playwright/reject-history.spec.js` — all 4 tests | E2E |
| AC-4 | static-analysis | grep audit: every `any` in `src/reject-history/` must carry `// TODO: type`; zero bare `any` or `@ts-ignore` | static-analysis |
| AC-5 | static-analysis | grep audit: zero `.js"` extension specifiers inside migrated SFCs in `src/reject-history/` | static-analysis |
| AC-6 | integration | `tests/test_frontend_compute_parity.py` — no stale `.js` paths for renamed reject-history files | integration |
| AC-6 | integration | `tests/test_frontend_duckdb_parity.py` — no stale `.js` paths for renamed reject-history files | integration |
| AC-7 | contract | `contracts/ci/ci-gate-contract.md` — schema-version == 1.3.5; `src/reject-history/**/*` in frontend-type-check scope | contract |

---

## Test File Inventory

### `frontend/tests/abort/reject-history-abort.test.js` (Vitest, jsdom)
- `abort before first poll prevents any apiGet calls`
- `abort during polling stops further apiGet calls`
- `deactivate sets isActive=false and destroys the client`
- `calling computeView after deactivate throws without mutating active state`
- `no error thrown when abort happens while component is already unmounted`
- `aborting active controller nulls it out (simulated runQuery cleanup)`

### `frontend/tests/components/ParetoGrid.test.js` (Vitest, jsdom)
- `renders without crash when paretoData is empty object`
- `renders without crash when paretoData is missing expected keys`
- `renders without crash when paretoData keys have no items array`
- `renders three ParetoSection stubs (one per dimension)`
- `emits item-toggle with dimension and value when ParetoSection triggers item-toggle`
- `passes loading prop down to ParetoSection children`

### `frontend/tests/legacy/reject-history-date-range-limit.test.js` (node:test)
- `reject-history date range validates half-year max days`

### `frontend/tests/validation/useRejectHistory.validation.test.js` (Vitest)
- `valid response with all optional fields present passes without warn`
- `valid response with optional fields null passes without warn`
- `valid response with optional fields absent passes without warn`
- `wrong type for total_lots (string) triggers console.warn`
- `wrong type for total_qty (boolean) triggers console.warn`
- `missing success field triggers envelope warn`
- `null data triggers warn`
- `valid response with pj_types array passes without warn`
- `valid response with empty pj_types array passes without warn`
- `pj_types as null (not array) triggers console.warn`
- `pj_types as string triggers console.warn`
- `missing pj_types triggers console.warn (required field)`
- `REJECT_HISTORY_SUMMARY_SCHEMA — accepts valid shape`
- `REJECT_HISTORY_SUMMARY_SCHEMA — warns on wrong type for total_qty`
- `REJECT_HISTORY_OPTIONS_SCHEMA — accepts valid array`
- `REJECT_HISTORY_OPTIONS_SCHEMA — rejects non-array pj_types`

### `frontend/tests/playwright/reject-history.spec.js` (Playwright)
- `page loads with filter panel visible`
- `executes query and renders results (date range mode)`
- `async job poll: handles 202 response path`
- `CSV export button triggers file download when data exists`

### `tests/test_frontend_compute_parity.py` (pytest — path audit)
- Audit only: verify no remaining hardcoded `.js` references to renamed reject-history files

### `tests/test_frontend_duckdb_parity.py` (pytest — path audit)
- Audit only: verify no remaining hardcoded `.js` references to renamed reject-history files

---

## Test Families Required

static-analysis, unit, data-boundary, integration, E2E, contract

---

## New Tests to Write

None. All migration risk is already covered by existing tests. Three maintenance steps are required but produce no new test files:

1. **`reject-history-abort.test.js` line 112** — update the import of `useRejectHistoryDuckDB.js` to the renamed `.ts` path (or bare specifier) after the file is renamed.
2. **`tests/test_frontend_compute_parity.py` + `test_frontend_duckdb_parity.py`** — update any hardcoded `.js` path references for `main.js` → `main.ts` and `useRejectHistoryDuckDB.js` → `useRejectHistoryDuckDB.ts` (per CLAUDE.md migration rule).
3. **AC-4 / AC-5 grep checks** — captured as gate steps in `ci-gates.md`; no new test file needed.

---

## Out of Scope

- Behavioral correctness of Pareto multi-dimension filter logic beyond what existing Vitest + Playwright already cover
- Performance or soak testing of DuckDB WASM queries
- Visual regression / screenshot diffing
- Migration of any other feature app (`hold-history/`, `resource-history/`, etc.)
- New unit tests for `useRejectHistoryDuckDB.ts` internal logic beyond what abort tests already exercise
- API contract tests (no API shape changes in this migration)
- Stress / resilience / monkey / soak testing (Tier 3 migration; not pre-merge)

---

## Notes

The abort test suite imports `useRejectHistoryDuckDB.js` directly (line 112). After rename this import must be updated or it will fail with a module-not-found error — see CLAUDE.md migration rule on auditing Vitest test files when renaming `.js` → `.ts`. The legacy `reject-history-date-range-limit.test.js` uses `node:test` (not Vitest); it must remain runnable via `node --test` in addition to passing inside the Vitest runner.
