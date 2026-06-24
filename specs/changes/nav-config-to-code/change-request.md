# Change Request

## Original Request

Collapse the runtime navigation / page-management CMS into a code-side source of truth, keeping ONLY a per-page visibility toggle in the admin UI (agreed "Option B").

**Background (from analysis in the originating session):**
- Mountable pages are already hardcoded in `frontend/src/portal-shell/nativeModuleRegistry.js` (route → component + CSS via native dynamic `import()`); per-route policy meta lives in `frontend/src/portal-shell/routeContracts.js`. The runtime layer (`data/page_status.json` + admin endpoints in `src/mes_dashboard/routes/admin_routes.py`, consumed by `frontend/src/portal-shell/navigationState.js`) only decides menu placement, ordering, display name, and a binary `released`/`dev` visibility gate.
- The runtime CMS is barely exercised: 20/21 pages are `released`, only `/admin/dashboard` is `dev`; drawer ids are auto-defaults (`drawer`, `drawer-2`, `drawer-3`) with an abandoned empty `test` drawer; there is **no per-user/role RBAC** (visibility is binary admin vs non-admin via `canViewPage`). The result is mostly unused machinery plus a 3-way config duplication (registry / routeContracts / page_status.json) that must be kept in sync.

**Scope (Option B):**
- **MOVE TO CODE** (single source of truth = a code-side navigation manifest): drawer definitions (id / name / order / admin_only), page→drawer assignment, page order, page display names.
- **REMOVE**: drawer CRUD endpoints (`POST/PUT/DELETE /api/drawers`) and the name/drawer_id/order mutation path of `PUT /api/pages/<route>`; retire the drawer-editing / reordering / renaming parts of the admin-pages frontend.
- **KEEP runtime + admin-frontend-configurable**: ONLY per-page `status` (released = visible to general users vs dev = admin-only). `PUT /api/pages/<route>` shrinks to status-only; the writable store shrinks from the full `page_status.json` CMS to a minimal `route → status` map; `GET /api/pages` stays (slimmed admin UI reads it to render a per-page visibility toggle list); `GET /api/drawers` is removed (drawers now come from code).
- **DATA MIGRATION**: port the current live menu layout into the code manifest, renaming auto-default drawer ids to meaningful ids and dropping the empty `test` drawer, so the user-visible menu is unchanged apart from cleanup.

**Deliverables**: update API + data + modernization contracts (`docs/migration/asset_readiness_manifest.json`, `docs/migration/route_scope_matrix.json`); regenerate affected admin contract samples (`get_admin_pages`, `get_admin_drawers`, `delete_admin_drawers_id`); update/retire `admin_routes` + `navigationState` tests; record the source-of-truth change (runtime CMS → code manifest) as an ADR.

**Success criteria (confirmed with requester):**
- **AC-1**: The navigation menu rendered to a non-admin user is structurally identical after the change (same drawers shown, same order, same page order within each drawer, same display names, same set of visible pages), now sourced entirely from the code manifest; only internal drawer ids are cleaned up (no user-visible change).
- **AC-2**: An admin can still set a page's status to `released`/`dev` from the admin-pages frontend; the change persists and takes effect on the next navigation load (page appears for / disappears from non-admins accordingly).
- **AC-3**: Drawer CRUD (`POST/PUT/DELETE /api/drawers`) and the name/drawer_id/order fields of `PUT /api/pages/<route>` are gone; the admin UI no longer offers drawer create/edit/reorder/rename.
- **AC-4**: API/data/modernization contracts and affected contract samples are updated; `admin_routes` + `navigationState` tests updated/retired; an ADR records the source-of-truth change; `cdd-kit gate` passes.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
