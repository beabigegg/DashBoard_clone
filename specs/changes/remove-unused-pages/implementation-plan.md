---
change-id: remove-unused-pages
schema-version: 0.1.0
last-changed: 2026-05-18
---

# Implementation Plan: remove-unused-pages

## Objective
Delete dead frontend apps (`tables`, `admin-performance`, `admin-user-usage-kpi`) and their wiring; add `production-history` to `vite.config.ts` `rollupOptions.input`. Keep Flask deprecated redirects for `/admin/performance` and `/admin/user-usage-kpi`. Prune contracts and tests in the same commit.

## Execution Scope

### In Scope
- Delete `frontend/src/tables/`, `frontend/src/admin-performance/`, `frontend/src/admin-user-usage-kpi/`.
- Edit `frontend/vite.config.ts`: remove `tables` entry; add `production-history` HTML entry.
- Edit portal-shell: `routeContracts.js`, `nativeModuleRegistry.js`, `style.css` (`.tables-page` rules), and any residual hits in `sidebarState.js`/`navigationState.js`/`router.js`/`routeQuery.js`.
- Remove Flask `/tables` route in `src/mes_dashboard/app.py` (lines 1015-1040).
- Remove `/tables` entry from `src/mes_dashboard/services/page_registry.py` (line 34); audit/edit `navigation_contract.py`.
- **KEEP** `admin_routes.py` `/performance` (lines 77-81) and `/user-usage-kpi` (lines 1204-1208) deprecated redirect stubs and their backing API endpoints (`/api/performance-*`, `/api/user-usage-kpi`) — they support `admin-dashboard`.
- Update contracts: `api-inventory.md`, `css-inventory.md`, `ci-gate-contract.md`, `CHANGELOG.md` per ci-gates.md "Contract version bumps".
- Delete + audit test files per test-plan.md "Test File Inventory".

### Out of Scope
- Removing Flask deprecated redirects or their backing APIs (Non-goal).
- Refactoring kept pages, page-registry data model, or navigation_contract schema.
- Visual/UI changes; new tests; new stress scenarios.
- Modifying `src/mes_dashboard/config/tables.py` (`TABLES_CONFIG` fixture is consumed by other routes — unrelated to the removed `/tables` SPA).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | contracts | Apply version bumps per ci-gates.md "Contract version bumps" and update inventories | backend-engineer |
| IP-2 | backend | Remove `/tables` route in `app.py`; remove `/tables` from `page_registry.py`; audit/edit `navigation_contract.py` | backend-engineer |
| IP-3 | backend tests | Update `tests/test_app_factory.py`, `test_template_integration.py`, `test_performance_integration.py`, `test_portal_shell_routes.py`, `test_page_registry.py`, `test_auth_integration.py`, `test_admin_routes.py`, `test_dashboard_routes.py` per test-plan.md audit table | backend-engineer |
| IP-4 | frontend build | Edit `frontend/vite.config.ts`: drop `tables` line; add `'production-history': resolve(__dirname, 'src/production-history/index.html')` | frontend-engineer |
| IP-5 | portal-shell | Delete `/tables` from `routeContracts.js` (line 12 array, lines 194-196 block) and `nativeModuleRegistry.js` (lines 65-68); delete `.tables-page` rules from `portal-shell/style.css` (lines 266-271+); grep `sidebarState.js`/`navigationState.js`/`router.js`/`routeQuery.js` for residual `tables`/`admin-performance`/`admin-user-usage-kpi` and remove | frontend-engineer |
| IP-6 | frontend app dirs | After grep confirms no kept-module imports, `rm -rf frontend/src/{tables,admin-performance,admin-user-usage-kpi}` | frontend-engineer |
| IP-7 | frontend tests | Delete `frontend/tests/legacy/admin-performance.test.js` and `admin-user-usage-kpi.test.js`; edit `loading-standardization.test.js` lines 222, 234 | frontend-engineer |
| IP-8 | e2e + stress tests | Delete 3 e2e files (test_admin_performance_e2e, test_admin_user_usage_kpi_e2e, test_tables_e2e); substitute `/tables` → `/production-history` in `test_admin_auth_e2e.py` and `test_frontend_stress.py`; delete `test_tables_page_loads` from `test_global_connection.py`; conditionally remove `('tables','result_table')` from `test_field_contracts.py` | backend-engineer |
| IP-9 | build verify | Run `cd frontend && npm run build`; capture `dist/` listing in agent log | frontend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | AC-1..AC-8 | scope and acceptance |
| test-plan.md | "Test File Inventory" Delete + Audit tables | exact files and line numbers |
| test-plan.md | "Build Verification (AC-3)" | AC-3 evidence procedure |
| ci-gates.md | "Required Gates" + "Contract version bumps" | gate commands and version targets |
| context-manifest.md | "Allowed Paths" / "Agent Work Packets" | read/write boundary |
| change-request.md | "Pre-audit findings", "Non-goals" | wiring deltas and keep-redirect decision |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| `frontend/src/tables/` | delete | whole dir, after IP-5 |
| `frontend/src/admin-performance/` | delete | grep first |
| `frontend/src/admin-user-usage-kpi/` | delete | grep first |
| `frontend/vite.config.ts` | edit | drop line 31 `tables`; add `production-history` HTML entry |
| `frontend/src/portal-shell/routeContracts.js` | edit | line 12 array + lines 194-196 contract block |
| `frontend/src/portal-shell/nativeModuleRegistry.js` | edit | lines 65-68 loader |
| `frontend/src/portal-shell/style.css` | edit | lines 266-271+ `.tables-page` rules |
| `frontend/src/portal-shell/sidebarState.js` | audit-then-edit | grep residual keys |
| `frontend/src/portal-shell/navigationState.js` | audit | grep residual keys |
| `frontend/src/portal-shell/router.js` | audit | grep residual keys |
| `frontend/src/portal-shell/routeQuery.js` | audit | grep residual keys |
| `src/mes_dashboard/app.py` | edit | delete `tables_page()` (lines 1015-1040) |
| `src/mes_dashboard/services/page_registry.py` | edit | remove line 34 `/tables` entry |
| `src/mes_dashboard/services/navigation_contract.py` | audit-then-edit | remove `/tables` if present |
| `src/mes_dashboard/routes/admin_routes.py` | audit-no-change | confirm redirects at lines 77-81 and 1204-1208 are preserved |
| `src/mes_dashboard/routes/dashboard_routes.py` | audit-no-change | grep confirmed zero `tables` refs |
| backend tests (8 files) | edit | exact lines in test-plan.md audit table |
| `tests/e2e/test_{admin_performance,admin_user_usage_kpi,tables}_e2e.py` | delete | per test-plan |
| `tests/e2e/test_global_connection.py` | edit | delete `test_tables_page_loads` (lines 129-130) |
| `tests/stress/test_frontend_stress.py` | edit | substitute `/tables` → `/production-history` (9 lines) |
| `tests/e2e/test_admin_auth_e2e.py` | edit | per test-plan audit table |
| `frontend/tests/legacy/{admin-performance,admin-user-usage-kpi}.test.js` | delete | per test-plan |
| `frontend/tests/legacy/loading-standardization.test.js` | edit | lines 222, 234 — delete two DataViewer blocks |
| `contracts/api/api-inventory.md` | edit | bump 1.1.5 → 1.1.6; line 48 row — note `/admin/performance` and `/admin/user-usage-kpi` are redirect-only stubs (HTTP 302 → `/admin/dashboard`), not SPA HTML; no `tables` entries exist (verified) |
| `contracts/css/css-inventory.md` | edit | add `schema-version: 1.2.0` frontmatter (currently missing), then bump to 1.2.1; delete lines 57, 58, 71 |
| `contracts/ci/ci-gate-contract.md` | edit | bump 1.3.14 → 1.3.15 with note: frontend-build scope reduced (removed 3 apps, added `production-history`) |
| `contracts/CHANGELOG.md` | edit | three patch entries matching the three bumps |

## Contract Updates
- API: `api-inventory.md` 1.1.5 → 1.1.6; line 48 row updated; no `tables` entries to remove (grep confirms).
- CSS/UI: `css-inventory.md` add `schema-version: 1.2.0` frontmatter FIRST (currently absent), then bump to 1.2.1; delete the 3 removed-app rows.
- Env: n/a
- Data shape: n/a
- Business logic: `business-rules.md` review only; expect no edit.
- CI/CD: `ci-gate-contract.md` 1.3.14 → 1.3.15.

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `ls frontend/src/{tables,admin-performance,admin-user-usage-kpi}` | errors (dirs absent) |
| AC-2 | `cd frontend && npm run build` | exit 0; no missing-input error |
| AC-3 | inspect `src/mes_dashboard/static/dist/` listing | `production-history.*` present; no `tables.*`/`admin-performance.*`/`admin-user-usage-kpi.*` |
| AC-4 | `pytest tests/test_app_factory.py tests/test_portal_shell_routes.py -x` | green |
| AC-5 | `pytest tests/test_app_factory.py tests/test_template_integration.py tests/test_performance_integration.py -x` | green |
| AC-6 | `cdd-kit validate` | green |
| AC-7 | `cd frontend && npm run test && npm run type-check`; `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | green |
| AC-8 | `cdd-kit gate remove-unused-pages` | green |

## Ordered Execution Sequence
1. Contracts: edit `api-inventory.md`, `css-inventory.md` (add then bump version), `ci-gate-contract.md`, `CHANGELOG.md`.
2. Backend source: edit `app.py` (`/tables` removal), `page_registry.py`, audit/edit `navigation_contract.py`.
3. Backend tests: update 8 audit files per test-plan; delete 3 e2e files; edit stress + global_connection + admin_auth_e2e.
4. Frontend wiring: edit `vite.config.ts`, `routeContracts.js`, `nativeModuleRegistry.js`, `portal-shell/style.css`; audit/edit other portal-shell modules.
5. Frontend tests: delete 2 legacy tests; edit `loading-standardization.test.js`.
6. Frontend app deletes: `rm -rf frontend/src/{tables,admin-performance,admin-user-usage-kpi}` (after grep across `frontend/src/` confirms zero residual imports).
7. Verify: `pytest`, `cd frontend && npm run test && npm run type-check && npm run css:check && npm run build`, `cdd-kit validate`, `cdd-kit gate remove-unused-pages`. Capture `dist/` listing in agent log.

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Source deletions and corresponding test updates must be in the **same commit** (atomic — `test_app_factory.py` line 53 is the must-fail-before test).
- Do NOT remove Flask `/performance` or `/user-usage-kpi` redirect stubs (Non-goal — explicit keep decision).
- Do NOT touch `frontend/<feature>/index.html` references to `./main.js` — pre-existing pattern (CLAUDE.md TypeScript Migration Rules).

## Known Risks
- Portal-shell may contain additional `tables`/`admin-performance`/`admin-user-usage-kpi` references beyond the four files greped during planning — frontend-engineer must rerun grep across `frontend/src/portal-shell/` before deletion; file a CER if hits appear in files outside the Allowed Paths.
- `css-inventory.md` currently lacks `schema-version` frontmatter — add 1.2.0 first, then bump to 1.2.1, to keep contract validators happy.
- `tests/stress/test_frontend_stress.py` substitution may invalidate stress baselines — informational only; stress is not a pre-merge gate (test-plan Out of Scope).
- `tests/test_field_contracts.py` `('tables','result_table')` removal is conditional on whether the `tables` field contract is eliminated entirely — backend-engineer must verify before editing.
