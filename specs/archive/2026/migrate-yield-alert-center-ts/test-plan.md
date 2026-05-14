---
change-id: migrate-yield-alert-center-ts
schema-version: 0.1.0
last-changed: 2026-05-14
risk: low
tier: 1
---

# Test Plan: migrate-yield-alert-center-ts

## Acceptance Criteria → Test Mapping

| AC | Test File | Test Name(s) | Tier |
|---|---|---|---|
| AC-1 | (toolchain) | `npm run type-check` — vue-tsc --noEmit zero errors | 1 |
| AC-2 | `frontend/tests/legacy/yield-alert-center-utils.test.js` | parseTokenList / toQueryParams / buildDrilldownNotice | 1 |
| AC-2 | `frontend/tests/abort/yield-alert-abort.test.js` | fetchParquetBuffer abort on signal (2 cases) / useYieldAlertDuckDB deactivate (2 cases) / job abort controller (2 cases) | 1 |
| AC-2 | `frontend/tests/yield-alert/App.cross-filter.test.js` | restores legacy departments param / requests cross-filter options after supplementary filter / restores sort and per-page from URL | 1 |
| AC-3 | `frontend/tests/legacy/yield-alert-center-shell-contract.test.js` | yield-alert-center route contract is native / launch href preserves query | 1 |
| AC-3 | `frontend/tests/validation/useYieldAlert.validation.test.js` | API envelope (5 cases) / DuckDB computeView output shapes (8 cases) / spool URL (5 cases) | 1 |
| AC-4 | `tests/test_frontend_duckdb_parity.py` | risk-score parity / yield_pct formula parity | 1 |
| AC-5 | (toolchain) | `npm run css:check` | 1 |
| AC-6 | All of AC-2, AC-3, AC-4 above | no behavior delta asserted by existing assertions | 1 |

## Test Families Required

unit / contract

## Required Test File Modifications (AC-2 scope only)

### `frontend/tests/legacy/yield-alert-center-utils.test.js`
- Line 8: `import ... from '../../src/yield-alert-center/utils.js'`
  → drop `.js` extension → `'../../src/yield-alert-center/utils'`
- File uses `node:test` / `assert` (no `require()`, no `vi.mock`). No regex assertions. No other changes needed.

### `frontend/tests/abort/yield-alert-abort.test.js`
- Line 106: dynamic `import('../../src/yield-alert-center/useYieldAlertDuckDB.js')`
  → drop `.js` → `'../../src/yield-alert-center/useYieldAlertDuckDB'`
- Line 125: same dynamic import path, same fix.
- Lines 18 / 28: `vi.mock('../../src/core/duckdb-client.js', ...)` and `vi.mock('../../src/core/risk-score.js', ...)` — these mock `src/core/` files already migrated to `.ts`; Vite resolves correctly with `.js` specifier in mocks, **no change required** per established pattern.
- No `require()` calls. No JS-specific regex assertions.

### `frontend/tests/yield-alert/App.cross-filter.test.js`
- Lines 17–36: all `vi.mock(...)` paths use `.js` specifiers pointing at already-migrated `src/core/` and `src/shared-composables/` files — these resolve correctly, **no change required**.
- Line 26: `vi.mock('../../src/yield-alert-center/useYieldAlertDuckDB.js', ...)` — mocks the file being renamed to `.ts`. Vite mock resolution with `.js` specifier works after rename; **no change required**.
- Dynamic `import('../../src/yield-alert-center/App.vue')` at lines 110, 172, 304 — `.vue` extension, unaffected.
- No `require()` calls. No JS-specific regex assertions.

### `frontend/tests/legacy/yield-alert-center-shell-contract.test.js` (AC-3 — must pass unmodified)
- Imports only `src/portal-shell/` files (not under migration scope). No changes needed or allowed.

### `frontend/tests/validation/useYieldAlert.validation.test.js` (AC-3 — must pass unmodified)
- Imports only `src/core/dev-warnings.js` and `src/core/schema-guard.js` (already migrated to `.ts`). No changes needed or allowed.

### `tests/test_frontend_duckdb_parity.py` (AC-4)
- References `frontend/src/core/risk-score.ts` (line 68, 156) — already `.ts`, not changed by this migration. No update needed.
- No hardcoded path to any `yield-alert-center/*.js` source file found.

## Out of Scope

- Logic changes inside any test file
- Adding new test cases
- Migrating test files themselves to TypeScript
- `src/core/` or `src/shared-composables/` files (already migrated in prior phases)

## Notes

Riskiest file: `yield-alert-abort.test.js` — dynamic imports of the renamed composable must resolve after rename. The `.js` specifier in `vi.mock` calls for already-migrated `src/core/` files is an established project pattern and must not be changed. Only the two dynamic `import()` calls for `useYieldAlertDuckDB.js` need extension dropped.
