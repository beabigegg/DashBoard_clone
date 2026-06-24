# Regression Report — nav-config-to-code

Durable safety proof that this refactor (navigation source-of-truth: runtime CMS → code manifest) introduces **no user-visible behavior change** (AC-1) and that all removed surfaces are gone safely. Evidence re-run live by qa-reviewer (not summary-trusted).

## Baseline
`current-behavior.md` captures the live rendered menu at change start (6 drawers, display names, page memberships, orders, the single `dev` page `/admin/dashboard`, the empty `test` drawer, standalone routes). It is the regression anchor.

## AC-1 / AC-5 — menu parity (no user-visible change)
The structure+status merge moved client-side, so parity is proven by a **built-nav-tree diff**, not an endpoint-shape check:
- `frontend/tests/legacy/portal-shell-navigation.test.js` — `buildDynamicNavigationState(manifest, statusMap)` structurally matches the `current-behavior.md` baseline for **non-admin** (5 drawers, `dev-tools` hidden, `/admin/dashboard` hidden) and **admin** (6 drawers incl. `dev-tools` with 2 pages): drawer ids cleaned, `test` drawer absent, display names verbatim, page memberships verbatim, drawer orders 1..6, trace-tools intra-drawer orders 1/2/3 (resolving the old 2/3/3 tie).
- `frontend/src/portal-shell/__tests__/navigationManifest.test.ts` — invariants: all drawer ids clean, distinct orders, every manifest route exists in `nativeModuleRegistry.js`, `defaultStatus:'dev'` only on `/admin/dashboard`.
- Result: vitest 613 passed / 0 fail; legacy parity 254 passed / 0 fail (live re-run).

## AC-2 — status toggle preserved (the one runtime capability kept)
- `tests/test_page_registry.py::TestSetPageStatus` — set/get `released`↔`dev` persists to and reflects from the shrunk `{api_public, statuses}` store.
- `frontend/tests/playwright/admin-pages.spec.ts` — admin status toggle round-trips via `PUT /admin/api/pages/{route}` (executes in the CI playwright gate).

## AC-3 / AC-7 — removed surfaces gone safely
- `tests/test_admin_routes.py` — `GET/POST/PUT/DELETE /admin/api/drawers` all return **404**; `PUT /admin/api/pages/<route>` accepts only `status` and rejects/ignores `name`/`drawer_id`/`order` (3 tests).
- `frontend/src/admin-pages/components/DrawerManagementPanel.vue` git-deleted; admin UI has no drawer create/edit/reorder/rename controls; no `GET /admin/api/drawers` call.

## AC-6 — back-compat + `api_public` (CRITICAL, no silent auth break)
- `tests/test_page_registry.py::TestShrunkStoreBackCompat` — a legacy full-CMS `page_status.json`, a missing file, and an absent route all fail safe to `released` (never error).
- `tests/test_page_registry.py::TestIsApiPublic::test_api_public_key_preserved_after_shrink` — **tripwire**: `api_public` survives the shrink and `is_api_public()` still reads it. Live `data/page_status.json` = `{api_public:true, statuses:{"/admin/dashboard":"dev"}}`.

## AC-4 / AC-8 — contracts, openapi, samples
- Both `contracts/openapi.json` and `contracts/api/openapi.json` regenerated and **drawer-path-free**; typed schemas `AdminPagesResponse` + `PortalNavigationResponse` added.
- 4 drawer samples retired (git `D`) + removed from `tests/contract/response-samples.json`; `get_admin_pages.json` slimmed; `get_portal_navigation.json` regenerated.
- `contracts/CHANGELOG.md` records `[api 1.27.0]`, `[data 1.24.0]`, `[ci 1.3.34]`. `cdd-kit validate --contracts` passes.

## Test execution summary
- Backend `pytest`: 133 passed. Frontend `vitest`: 613 passed / 2 skipped; legacy 254 passed; `vue-tsc` 0 errors.
- `test-evidence.yml`: required phases collect / targeted / changed-area / contract all `passed`, `final-status: passed`, no waiver fields.

## Residual risks (non-blocking; follow-up)
- **Legacy `portal_index()` (`src/mes_dashboard/app.py:1060`)** passes the new status dict as `drawers=` to `portal.html`. Verified **inert**: `PORTAL_SPA_ENABLED` defaults `True` (`config/settings.py:79`), so the SPA shell is always served; the non-SPA branch is only reachable under an explicit deprecated `PORTAL_SPA_ENABLED=false` opt-out, where Jinja `| default([])` degrades rather than 500s. Follow-up: drop the dead non-SPA branch (owner: backend-engineer).
- **Orphaned CSS** in `frontend/src/admin-pages/style.css` (drawer-era rules from the deleted panel) — dead, still `.theme-`-scoped (css:check Rule 6 satisfied). Cleanup recommended same-PR (owner: frontend).
- **a11y** (ui-ux, low): status toggle button lacks `aria-pressed`; error panel lacks `role="alert"`. Admin-only surface; follow-up.

## Conclusion
No user-visible navigation regression: the rendered menu is byte-equivalent (display names/order/membership/visibility) for admin and non-admin, proven by the built-tree parity tests against the captured baseline. Removed admin surfaces return 404 and the admin UI is cleanly reduced. The auth-adjacent `api_public` gate is preserved with a dedicated tripwire. Safe to merge once `cdd-kit gate` passes.
