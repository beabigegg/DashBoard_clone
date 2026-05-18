---
change-id: remove-unused-pages
closed: 2026-05-18
status: complete
---

# Archive: remove-unused-pages

## Change Summary

Removed three orphaned frontend SPAs (`tables`, `admin-performance`, `admin-user-usage-kpi`) and all their wiring across vite config, portal-shell routing (routeContracts.js, nativeModuleRegistry.js, style.css), Flask Blueprint (`/tables` route), and page registry. Fixed `production-history` missing from `vite.config.ts` `rollupOptions.input`. Flask deprecated redirects for `/admin/performance` and `/admin/user-usage-kpi` were retained per explicit Non-goal decision. Three follow-up commits fixed post-deploy runtime regressions: gunicorn startup crash (`asset_readiness_manifest.json` still listed `/tables`), sidebar showing stale `/tables` entry (`data/page_status.json` not updated), and 6 pre-existing CSS HEX violations in `EquipmentRejectsTable.vue`.

## Final Behavior

- Navigating to `/tables` returns 404 (Blueprint removed).
- `/admin/performance` and `/admin/user-usage-kpi` return HTTP 302 → `/admin/dashboard` (redirects kept).
- `/production-history` is now included in the vite build and correctly bundled.
- Sidebar no longer shows "表格總覽" (tables entry removed from `data/page_status.json`).
- `css:check` now exits 0 errors (was 6 pre-existing HEX violations).

## Final Contracts Updated

| contract | version bump | change |
|---|---|---|
| `contracts/api/api-inventory.md` | 1.1.5 → 1.1.6 | `/admin/performance` and `/admin/user-usage-kpi` documented as redirect-only stubs |
| `contracts/css/css-inventory.md` | missing → 1.2.0 → 1.2.1 | Added missing `schema-version` frontmatter; removed 3 deleted-app style entries |
| `contracts/ci/ci-gate-contract.md` | 1.3.14 → 1.3.15 | frontend-build scope note: 3 apps removed, production-history added |
| `contracts/CHANGELOG.md` | — | 3 patch entries for the 3 version bumps |

## Final Tests Added / Updated

Deleted (5 files):
- `frontend/tests/legacy/admin-performance.test.js`
- `frontend/tests/legacy/admin-user-usage-kpi.test.js`
- `tests/e2e/test_admin_performance_e2e.py`
- `tests/e2e/test_admin_user_usage_kpi_e2e.py`
- `tests/e2e/test_tables_e2e.py`

Audited (11 files — exact lines removed per test-plan.md audit table):
- `tests/test_app_factory.py` (must-fail-before test: `/tables` removed from `expected` set)
- `tests/test_template_integration.py`
- `tests/test_performance_integration.py`
- `tests/test_portal_shell_routes.py`
- `tests/test_page_registry.py`
- `tests/test_auth_integration.py`
- `tests/test_field_contracts.py`
- `tests/e2e/test_admin_auth_e2e.py` (→ `/production-history`)
- `tests/e2e/test_global_connection.py` (deleted `test_tables_page_loads`)
- `tests/stress/test_frontend_stress.py` (9 occurrences → `/production-history`)
- `frontend/tests/legacy/loading-standardization.test.js` (2 DataViewer blocks deleted)

## Final CI/CD Gates

| gate | result |
|---|---|
| pytest | 3931 passed, 132 skipped |
| vitest | 346 passed, 1 skipped |
| type-check | exit 0 |
| css:check | 0 errors (after EquipmentRejectsTable.vue fix) |
| npm run build | exit 0; production-history.js present; no tables/admin-performance/admin-user-usage-kpi chunks |
| cdd-kit validate | all passed |
| cdd-kit gate --strict | passed |

## Production Reality Findings

1. **`admin-user-usage-kpi/components/` had a hidden dependency**: `admin-dashboard/tabs/UsageTab.vue` imports 7 Vue components from this directory. The implementation plan said to delete the entire `admin-user-usage-kpi/` directory. The frontend-engineer agent discovered the cross-app import at build time and correctly restored the `components/` subdirectory. Only SPA entry files (App.vue, main.js, index.html, style.css) were deleted. The directory now functions as an undocumented shared component library consumed solely by admin-dashboard.

2. **`asset_readiness_manifest.json` not in change scope**: The modernization policy infrastructure file at `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json` still listed `/tables: ["tables.js"]`. At startup, `_validate_in_scope_asset_readiness()` in `app.py` read this manifest and raised `RuntimeError`, crashing all gunicorn workers. This file was not in the original Allowed Paths. Fix: removed `/tables`, added `/production-history`. Also updated `route_scope_matrix.json` in the same directory.

3. **`data/page_status.json` runtime state not in change scope**: The page registry's persisted JSON file (`data/page_status.json`) still held a `/tables` entry (`drawer_id: dev-tools`). The backend navigation API returned this entry at runtime, causing the portal-shell to warn "缺少 route contract: /tables" and render the stale sidebar item. This file is not tracked as source code for page-removal changes; it must be cleaned explicitly.

## Lessons Promoted to Standards

All three lessons promoted to `CLAUDE.md` as guidance (no contract schema-version bumps required).

| lesson | target | section | evidence |
|---|---|---|---|
| A — `asset_readiness_manifest.json` and `route_scope_matrix.json` must be updated on page add/remove | `CLAUDE.md` | `## Modernization Policy Artifact Notes` (new section) | `src/mes_dashboard/core/modernization_policy.py:17-21`; gunicorn startup crash post-deploy |
| B — `data/page_status.json` runtime registry must be cleaned on page remove | `CLAUDE.md` | `## Modernization Policy Artifact Notes` (second bullet) | `src/mes_dashboard/services/page_registry.py:18`; sidebar ghost entry post-deploy |
| C — `admin-user-usage-kpi/components/` is a build-time dependency of `admin-dashboard` | `CLAUDE.md` | `## Shared UI Component Notes` (new bullet) | `frontend/src/admin-dashboard/tabs/UsageTab.vue:4-10`; Vite build break on deletion |

## Follow-up Work

- `frontend/src/admin-user-usage-kpi/components/` is now a de-facto shared component library (7 components) consumed only by `admin-dashboard`. A future cleanup should either move these components into `admin-dashboard/` directly or into `shared-ui/`. Non-blocking.
- `drawer-2`, `drawer-3`, `drawer` drawer IDs in `page_status.json` are non-semantic legacy IDs. The `reports`, `queries`, `dev-tools` drawers in `DEFAULT_DRAWERS` are the canonical set. Migration deferred.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
