---
change-id: migrate-admin-shared-ts
schema-version: 0.1.0
last-changed: 2026-05-12
risk: low
tier: 3
---

# Test Plan: migrate-admin-shared-ts

## Acceptance Criteria → Test Mapping

| criterion id | test family   | test file path                                          | test name                                                   | tier |
|---|---|---|---|---|
| AC-1         | contract      | (npm run type-check)                                    | tsc — zero errors across admin-shared/                      | 3    |
| AC-2         | contract      | (npm run type-check)                                    | tsc — SFC script lang="ts" type-checks cleanly              | 3    |
| AC-3         | contract      | (npm run type-check)                                    | tsc — full frontend scope zero errors                       | 3    |
| AC-4         | unit          | frontend/tests/legacy/admin-dashboard.test.js           | admin dashboard has six tabs                                | 3    |
| AC-4         | unit          | frontend/tests/legacy/admin-dashboard.test.js           | each tab has a unique key                                   | 3    |
| AC-4         | unit          | frontend/tests/legacy/admin-performance.test.js         | (all tests in file)                                         | 3    |
| AC-4         | unit          | frontend/tests/legacy/admin-user-usage-kpi.test.js      | (all tests in file)                                         | 3    |
| AC-5         | integration   | (npm run build)                                         | Vite build exits 0 — no resolution failures                 | 3    |
| AC-6         | contract      | (npm run css:check)                                     | CSS governance — no path or class regressions               | 3    |
| AC-7         | contract      | (npm run type-check)                                    | barrel index.ts exports all 4 components + 1 composable     | 3    |
| AC-8         | contract      | (npm run type-check)                                    | consumer imports in admin-dashboard/, admin-performance/ resolve without .js specifiers | 3 |
| AC-9         | contract      | (npm run type-check)                                    | no bare `as any`; declared-interface pattern for cross-phase imports | 3 |
| AC-10        | unit          | frontend/tests/legacy/admin-*.test.js (all three)       | all legacy tests remain green after rename                  | 3    |
| AC-11        | contract      | (manual audit — no Python parity tests reference admin-shared) | n/a — vacuously satisfied; no .js paths to update    | 3    |
| AC-12        | gate          | (cdd-kit gate migrate-admin-shared-ts --strict)         | all CI gates pass                                           | 3    |

## Test Families Required

contract / unit / integration / gate

## Notes

- Legacy tests (`admin-dashboard.test.js`, `admin-performance.test.js`, `admin-user-usage-kpi.test.js`) test inline utility functions copied from their respective apps; they do not import from `admin-shared/` directly. No path specifiers need updating in these files.
- Vitest config (`vitest.config.js`) excludes `tests/legacy/**` — legacy tests run via `node:test` runner independently. Both suites must stay green.
- No Python parity tests (`test_frontend_compute_parity.py`, `test_frontend_duckdb_parity.py`) reference `admin-shared/`; AC-11 requires only confirming this remains true after migration.
- No new test files are required for this Tier 3 refactor. All coverage is provided by the type-checker, build tool, CSS checker, and the three existing legacy test files.

## Out of Scope

- New Vitest component-mount tests for GaugeBar, StatCard, StatusDot, TrendChart
- E2E / Playwright tests for admin pages
- Python parity tests (no compute logic in admin-shared/)
- Migration of consumer directories (admin-dashboard/, admin-performance/, admin-user-usage-kpi/)
