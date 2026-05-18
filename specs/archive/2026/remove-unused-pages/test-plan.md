---
change-id: remove-unused-pages
schema-version: 0.1.0
last-changed: 2026-05-18
risk: medium
tier: 1
---

# Test Plan: remove-unused-pages

## Acceptance Criteria — Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (dirs removed) | unit | verified implicitly: `npm run test` fails if `readSrc('tables/...')` resolves | 0 |
| AC-2 (vite config patched) | build-verification | `cd frontend && npm run build` — no error on missing entries | 1 |
| AC-3 (dist bundle correct) | build-verification | manual inspect `dist/` for `production-history` present, `tables`/`admin-performance`/`admin-user-usage-kpi` absent | 1 |
| AC-4 (portal routes gone) | integration | `tests/test_app_factory.py::test_routes_registered`; `tests/test_portal_shell_routes.py` line 462 | 1 |
| AC-5 (Flask blueprint removed) | integration | `tests/test_app_factory.py`, `tests/test_template_integration.py` lines 83-88/287-296/343/358, `tests/test_performance_integration.py` lines 53/375-404 | 1 |
| AC-6 (contracts pruned) | contract | `cdd-kit validate` after editing `api-inventory.md` and `css-inventory.md` | 1 |
| AC-7 (test suite clean) | unit + e2e | see "Test File Inventory" section | 0/1 |
| AC-8 (gate passes) | contract | `cdd-kit gate remove-unused-pages` | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Vitest legacy suite green after deletions; `npm run test` + `npm run type-check` |
| integration | 1 | `pytest` green after route/blueprint removal and all audit edits |
| contract | 1 | `cdd-kit validate` + `cdd-kit gate remove-unused-pages` |
| build-verification | 1 | `npm run build` + manual dist/ filename inspection for AC-3 |

## Test File Inventory

### Delete (all confirmed on disk)

| file | reason |
|---|---|
| `frontend/tests/legacy/admin-performance.test.js` | tests removed app |
| `frontend/tests/legacy/admin-user-usage-kpi.test.js` | tests removed app |
| `tests/e2e/test_admin_performance_e2e.py` | e2e for removed page |
| `tests/e2e/test_admin_user_usage_kpi_e2e.py` | e2e for removed page |
| `tests/e2e/test_tables_e2e.py` | e2e for removed page |

No `frontend/tests/legacy/tables.test.js` exists — no deletion needed there.

### Audit (update specific lines, do not delete files)

| file | lines referencing removed pages | required action |
|---|---|---|
| `tests/test_app_factory.py` | line 53: `"/tables"` in `expected` set | Remove `/tables` from set — **must-fail-before test** |
| `frontend/tests/legacy/loading-standardization.test.js` | lines 222, 234: `readSrc('tables/components/DataViewer.vue')` | Delete the two DataViewer test blocks |
| `tests/test_template_integration.py` | lines 83-88, 287-296, 343, 358 | Remove assertions referencing `/tables` route and `tables.js` |
| `tests/test_performance_integration.py` | lines 53, 375, 381 (`/admin/performance`); lines 399, 404 (`/admin/user-usage-kpi`) | Remove page-route assertions; keep any API-only assertions |
| `tests/test_portal_shell_routes.py` | line 462: `/tables?category=wip` redirect mapping | Remove that mapping entry |
| `tests/test_page_registry.py` | lines 24, 64-65, 178: `/tables` fixture and assertions | Remove `/tables` fixture entry and dependent assertions |
| `tests/test_auth_integration.py` | lines 248, 252, 258, 264 | Remove `/tables` page-append and `GET /tables` test cases |
| `tests/e2e/test_admin_auth_e2e.py` | lines 33, 162, 185, 237-261, 279, 304 | Remove `/tables` references; substitute a kept route in page-enable/disable tests |
| `tests/e2e/test_global_connection.py` | lines 129-130: `test_tables_page_loads` | Delete that test method |
| `tests/stress/test_frontend_stress.py` | lines 54, 73, 98, 119, 150, 182, 221, 447, 474 | Substitute `/tables` with a kept route (e.g., `/production-history`) |
| `tests/test_field_contracts.py` | lines 28, 58: `('tables', 'result_table')` | Remove entries if `tables` field contract is eliminated |

## Build Verification (AC-3)

Command: `cd frontend && npm run build`

Pass criteria — inspect `dist/` filenames:
- Present: entry chunk containing `production-history`
- Absent: entry chunks named `tables`, `admin-performance`, `admin-user-usage-kpi`

No automated file-name assertion test exists; document `dist/` listing in the agent log as evidence.

## Out of Scope

- Flask deprecated redirects for `/admin/performance` and `/admin/user-usage-kpi` (kept per Non-goals; no removal test required).
- Oracle/DuckDB/Redis data layers — unaffected surfaces.
- Visual / screenshot regression — no UI surface changes.
- New stress scenarios — existing stress tests updated (route substituted) but no new load test added.

## Notes

`tests/test_app_factory.py::test_routes_registered` is the must-fail-before test: it currently asserts `/tables` is registered and must fail immediately after Blueprint removal. Patch the `expected` set in the same commit that removes the Blueprint. All Tier 1 gate commands: `pytest`, `cd frontend && npm run test`, `cd frontend && npm run type-check`, `cdd-kit validate`.
