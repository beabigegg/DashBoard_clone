# Contract Edit Spec (contract-reviewer → backend-engineer)

Authoritative, file-by-file contract edits to APPLY. Verdict: changes-required.
Routes are under `/admin/api/...` (not `/api/...`). Honor api-contract.md §Schema Authoring Rules (bare-identifier schema cells; `| field | type | required |` Tier-A tables; **regen openapi.json after endpoint-table edits**; version entries → contracts/CHANGELOG.md only).

## 1. contracts/api/api-contract.md
- **Remove** the 4 drawer rows from the §4 endpoint table: `GET /admin/api/drawers`, `POST /admin/api/drawers`, `PUT /admin/api/drawers/{drawer_id}`, `DELETE /admin/api/drawers/{drawer_id}`.
- **Add** a row (was undocumented): `| PUT | /admin/api/pages/{route} | admin | JSON body {status} | AckResponse | 400/403/404 | route tests |`.
- **Change** the `GET /admin/api/pages` response cell `GenericSuccessResponse` → `AdminPagesResponse`.
- **Change** the `GET /api/portal/navigation` response cell → `PortalNavigationResponse`.
- **Add 2 schemas** under `## Schemas`:
  - `AdminPagesResponse` (Tier-B): `data.pages[]` of `{route:string, status:enum[released,dev]}`; envelope success/data/meta.
  - `PortalNavigationResponse` (Tier-B): `data` = `{ statuses: map<route, enum[released,dev]> (additionalProperties), is_admin:bool, admin_user:string|null, admin_links:array, features:object, diagnostics:object }`. `drawers` REMOVED. Note: route absent from `statuses` defaults to `released`.
- **Add** a `## Compatibility Notes` entry (nav-config-to-code, 2026-06-24): breaking removal of the 4 drawer endpoints (all return **404**); `PUT /admin/api/pages/{route}` body narrows to `{status}` (name/drawer_id/order silently ignored, MUST NOT persist); `GET /admin/api/pages` narrows to `{pages:[{route,status}]}`; `/api/portal/navigation` drops `drawers`, adds `statuses`; sole consumers `frontend/src/admin-pages/` + `portal-shell/` (monorepo atomic cutover, no deprecation window).
- **Inline `## CHANGELOG`**: prepend `[api 1.27.0] — 2026-06-24` (Removed: 4 drawer endpoints + name/drawer_id/order from GET pages response & PUT pages body; Changed: portal/navigation shape + new schemas; Added: PUT /admin/api/pages row).

## 2. contracts/api/api-inventory.md (bump 1.2.4 → 1.2.5)
- Update the `admin_routes.py` row: list `GET /admin/api/pages` (slimmed), `PUT /admin/api/pages/<route>` (status only), existing user-usage-kpi + analytics/recalculate; mark **REMOVED (nav-config-to-code)**: the 4 drawer endpoints.
- Update `legacy-transition` row: `app.py | /api/portal/navigation | Status feed; returns {statuses, is_admin, admin_user, admin_links, features, diagnostics}; drawers dropped`.
- Prepend a Compatibility Note (2026-06-24).

## 3. contracts/data/data-shape-contract.md (bump 1.23.1 → 1.24.0)
- **New §3.11a Writable Page-Status Store (`data/page_status.json`)**: target shape `{ "api_public": bool (REQUIRED — read by is_api_public(); default false if absent; MUST NOT drop), "statuses": { route: "released"|"dev" } (optional; absent route → released) }`. REMOVED keys: `pages`, `drawers`, `db_scan`. **Back-compat read**: if file is old full-CMS shape, derive statuses from `pages[].status`, no error, no forced rewrite. Write path: `set_page_status(route,status)` writes only `statuses`. Rollback-safe (restored `_migrate_navigation_schema` rebuilds drawers from DEFAULT_DRAWERS).
- **New §3.11b Navigation Manifest (`frontend/src/portal-shell/navigationManifest.js`)**: exports `drawers[]` of `{id, name, order, admin_only}` + `routes` map `route → {drawerId, order, displayName, defaultStatus}`. Drawer id rename: reports(keep), drawer-2→history-reports, drawer→query-tools, drawer-3→trace-tools, dev-tools(keep), eap-analysis(keep), **drop `test`**. Drawer orders 1..6: reports=1, history-reports=2, query-tools=3, trace-tools=4, dev-tools=5, eap-analysis=6. Within trace-tools: query-tool=1, mid-section-defect=2, material-trace=3. Standalone (`/`, `/wip-detail`, `/hold-detail`, `/anomaly-overview`) → drawerId null / absent. Only `/admin/dashboard` has `defaultStatus:'dev'`; all others `released`. Constraints: every manifest route MUST exist in nativeModuleRegistry.js; orders distinct within a drawer; displayName MUST match current live names (AC-1/AC-5).
- **New §2.10 `GET /admin/api/pages` slimmed** payload example (`{pages:[{route,status}]}`; name/drawer_id/order absent; one row per registered route; admin-only).
- **New §2.11 `GET /api/portal/navigation` status feed** payload example (`{statuses, is_admin, admin_user, admin_links, features, diagnostics}`; no drawers).

## 4. contracts/business/business-rules.md
- No rule change. Optional one-line pointer to data-shape §3.11a/§3.11b (released/dev semantics unchanged; only storage location moved). May be omitted.

## 5. contracts/ci/ci-gate-contract.md — DONE by ci-cd-gatekeeper (gate compat note + stale material-consumption fix + bump 1.3.34).

## 6. contracts/CHANGELOG.md — prepend 3 entries:
- `[api 1.27.0] — 2026-06-24` (Removed BREAKING: 4 drawer endpoints → 404; name/drawer_id/order removed from GET pages response & PUT pages body. Changed: portal/navigation shape + PortalNavigationResponse. Added: AdminPagesResponse + PUT /admin/api/pages row. No deprecation window — monorepo atomic.)
- `[data 1.24.0] — 2026-06-24` (Changed BREAKING: page_status.json → {api_public, statuses}; api_public preserved; back-compat read. Added: §3.11b manifest, §2.10/§2.11 payloads.)
- `[ci 1.3.34] — 2026-06-24` (retire 4 drawer samples + response-samples.json entries; regen get_admin_pages + get_portal_navigation samples.)

## 7. Modernization manifests — NO structural edit (verified): `/admin/pages` stays a route entry in asset_readiness_manifest.json + route_scope_matrix.json; no page add/remove.

## openapi (Schema Authoring Rule 4) — regen BOTH after the table edits:
`cdd-kit openapi export --out contracts/openapi.json` AND `--out contracts/api/openapi.json`. Both currently contain drawer paths + must end drawer-path-free (openapi-sync gate enforces).

## Contract samples (lockstep with endpoint removal):
- Retire files: `tests/contract/samples/{get_admin_drawers,delete_admin_drawers_id,post_admin_drawers,put_admin_drawers_id}.json`.
- Remove all 4 drawer entries from `tests/contract/response-samples.json`.
- Regenerate `tests/contract/samples/get_admin_pages.json` (slim {route,status} only).
- Regenerate `tests/contract/samples/get_portal_navigation.json` (statuses map, no drawers).
- Point response-samples.json: GET /admin/api/pages → AdminPagesResponse; /api/portal/navigation → PortalNavigationResponse.

## CRITICAL risk (machine-check it): dropping `api_public` from page_status.json silently disables `is_api_public()` site-wide auth bypass. Pin with §3.11a MUST + a `is_api_public()` preservation unit test.
