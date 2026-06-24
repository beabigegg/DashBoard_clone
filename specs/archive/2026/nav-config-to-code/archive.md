# Archive — nav-config-to-code

## Change Summary
Collapsed the runtime navigation/page-management CMS into a code-side single source of truth. Drawer structure, ordering, display names, and page→drawer assignment moved into `frontend/src/portal-shell/navigationManifest.js`; the only runtime-writable surface left is a per-page `status` (released/dev) toggle in the admin UI. Motivation: the runtime CMS had no per-user RBAC, was barely used (20/21 pages released, junk auto-default drawer ids), and forced a 3-way config duplication (nativeModuleRegistry / routeContracts / page_status.json) that had to be kept in sync.

## Final Behavior
- `GET /api/portal/navigation` returns a **status feed** `{statuses: route→status, is_admin, admin_user, admin_links, features, diagnostics}` — no `drawers`. The structure+status merge moved **client-side** into `navigationState.js`.
- Drawer CRUD endpoints (`GET/POST/PUT/DELETE /admin/api/drawers`) removed (404). `PUT /admin/api/pages/<route>` accepts only `status`. `GET /admin/api/pages` returns `{pages:[{route,status}]}`.
- `data/page_status.json` shrunk to `{api_public, statuses}` with legacy full-CMS back-compat read (fail-safe to `released`). `api_public` (the `is_api_public()` auth gate) preserved.
- Non-admin rendered menu unchanged (display names/order/membership verbatim; internal drawer ids cleaned up, empty `test` drawer dropped).

## Final Contracts Updated
- `contracts/api/api-contract.md` (1.26.0→1.27.0): removed 4 drawer rows, added `PUT /admin/api/pages` row, `AdminPagesResponse` + `PortalNavigationResponse` schemas, compat note.
- `contracts/api/api-inventory.md` (1.2.4→1.2.5); `contracts/data/data-shape-contract.md` (1.23.1→1.24.0): §2.10/§2.11 payloads, §3.11a store, §3.11b manifest.
- `contracts/ci/ci-gate-contract.md` (1.3.33→1.3.34); `contracts/CHANGELOG.md` (api/data/ci entries); both `contracts/openapi.json` + `contracts/api/openapi.json` regenerated drawer-free.
- ADR `docs/adr/0012-navigation-source-of-truth-code-manifest.md`.
- Modernization manifests: NO change (page stays; no add/remove) — verified.

## Final Tests Added / Updated
- New: `frontend/src/portal-shell/__tests__/navigationManifest.test.ts` (AC-5 invariants); nav-tree parity tests in `frontend/tests/legacy/portal-shell-navigation.test.js` (AC-1 admin+non-admin vs baseline).
- Backend: `tests/test_admin_routes.py` (drawer 404 + PUT field-rejection), `tests/test_page_registry.py` (`TestShrunkStoreBackCompat`, `test_api_public_key_preserved_after_shrink` tripwire), `tests/test_app_factory.py`, `tests/test_auth_integration.py`.
- Realigned to new shapes (CI-caught): `tests/test_portal_shell_routes.py` (8), `tests/test_modernization_policy_hardening.py` (2), `tests/test_reject_history_shell_coverage.py` (1).
- Deleted: `TestDrawerCrud`, `TestSchemaMigration`, `DrawerManagementPanel.vue` + its Playwright tests. Contract samples: 4 drawer samples retired; `get_admin_pages`/`get_portal_navigation` regenerated.
- Evidence: backend pytest 133 (ladder) / full suite **4885 passed, 0 failures**; frontend vitest 613; `vue-tsc` 0.

## Final CI/CD Gates
Per `ci-gates.md`: `response-shape-validate`, `unit-mock-integration` (→ CI `unit-and-integration-tests`), `frontend-unit`, `playwright-critical-journeys`, `openapi-sync`. PR #6 (DashBoard_clone) — all 7 checks green after the fix round; merged squash `b66390af`.

## Production Reality Findings
1. **Architecture review corrected the surface**: the real general-user menu source is `GET /api/portal/navigation` (`app.py::portal_navigation_config`), NOT `/api/drawers` (the admin-CMS editor). Classifier + my initial framing missed this; spec-architect's CER-003 caught it.
2. **`api_public` landmine**: `page_status.json` also gates `is_api_public()` (site-wide auth bypass); a naive "shrink to route→status" would have silently disabled it. Pinned by a tripwire test + data-shape MUST.
3. **Local gate ≠ CI**: `cdd-kit gate --strict` passed locally but CI failed twice — (a) `openapi-sync` (`openapi export --check`) caught an openapi drift the local gate did not flag after a schema-version bump; (b) `unit-and-integration-tests` (full suite) caught 11 pre-existing tests asserting old behavior that the bounded ladder (changed-area only) never ran. Both fixed; CI green round 2.
4. **Sample churn**: running the full suite re-runs `test_capture_samples`, regenerating ~all contract samples with live runtime values — reverted twice to keep the diff tight.

## Lessons Promoted to Standards
All 3 candidates evidence-gated by contract-reviewer (guidance-only; no contract schema-version bumps):
1. **Local gate ≠ full suite** → CLAUDE.md "Test coverage discipline" (new line) + `docs/cdd-kit-patterns.md` §"Local Gate vs CI Full Suite — Stale Tests on Removals". Evidence: CI `unit-and-integration-tests` failed with 11 stale tests that `cdd-kit gate --strict` passed.
2. **Full-suite re-captures all contract samples** → CLAUDE.md "CDD Kit operations" (new line) + `docs/cdd-kit-patterns.md` §"Full Pytest Suite Regenerates All Contract Samples". Evidence: ~166 then ~160 sample files reverted twice.
3. **openapi dual-file + schema-version drift** → folded into CLAUDE.md line 112 (canonical detail in `contracts/api/api-contract.md §Schema Authoring Rules`). Evidence: CI `openapi-sync` (`openapi export --check`) failed after a schema-version bump the local gate did not flag.

## Follow-up Work (non-blocking, recorded in regression-report.md)
- Legacy `portal_index()` (`app.py:1060`) passes the status dict as `drawers=` to `portal.html` — inert (`PORTAL_SPA_ENABLED` defaults True); drop the dead non-SPA branch.
- Orphaned drawer-era CSS in `frontend/src/admin-pages/style.css`; minor a11y (`aria-pressed`, `role="alert"`) on the admin surface.

## Cold Data Warning
This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
