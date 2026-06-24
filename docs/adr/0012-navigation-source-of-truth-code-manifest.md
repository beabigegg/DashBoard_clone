# ADR 0012: navigation source-of-truth moved from runtime CMS to code manifest

## Status
proposed

## Context
Portal navigation **structure** — drawer id/name/order/admin_only, page→drawer
assignment, page order, and page display name — has lived in a runtime CMS:
`data/page_status.json` (a writable JSON store), mutated through admin endpoints
`POST/PUT/DELETE /api/drawers` and the `name`/`drawer_id`/`order` fields of
`PUT /api/pages/<route>`, served to the menu by `app.py::portal_navigation_config()`
(`GET /api/portal/navigation`) which merges that structure with a per-page
`released`/`dev` status and re-normalizes it again client-side in
`navigationState.js`. This duplicates configuration three ways
(`nativeModuleRegistry.js` mount gate / `routeContracts.js` policy meta /
`page_status.json` placement) that must be kept in sync, while the CMS is barely
exercised: 20/21 pages are `released`, the one live status use is
`/admin/dashboard:'dev'`, drawer ids are auto-generated (`drawer`, `drawer-2`,
`drawer-3`) with an abandoned empty `test` drawer, and there is no per-user/role
RBAC (visibility is binary admin vs non-admin). The structure is, in practice,
static configuration masquerading as runtime state.

## Decision
Make a **code-side navigation manifest** (`frontend/src/portal-shell/navigationManifest.js`)
the single source of truth for navigation *structure*. Keep runtime-writable only
the per-page binary `status`; shrink `data/page_status.json` to a route→status map.
Remove drawer CRUD (`POST/PUT/DELETE /api/drawers`, `GET /api/drawers`) and the
structure fields of `PUT /api/pages/<route>` (status-only). The structure+status
**merge relocates from the server to the client**: `GET /api/portal/navigation`
stops emitting drawers and instead returns the route→status map (plus the
auth-derived `is_admin`/`admin_user`/`admin_links`/`features` it already owns), and
`navigationState.js` merges manifest structure × status map. Reads fail safe to
visible (`released`) on a missing/legacy/partial store, mirroring the existing
default. Auto-default drawer ids are renamed to meaningful ids and the empty
`test` drawer is dropped, with explicit distinct orders that reproduce the current
rendered layout 1:1 (no user-visible change).

## Consequences
- The 3-way config duplication collapses: `nativeModuleRegistry` remains the mount
  gate, `routeContracts` remains policy meta, and the manifest owns placement —
  each route's structure is declared once.
- The general-user menu (AC-1) becomes a pure function of the manifest plus the
  status map. Its regression proof is a client-side built-nav-tree diff, not a
  server response diff; a manifest typo silently breaks the menu with no backend
  signal, so menu-parity tests must assert the rendered nav tree.
- Drawer reconfiguration is now a code change + deploy, not a runtime admin action.
  This is intentional (the capability was unused and unsafe — no RBAC), but it is a
  **capability reduction** that must not be silently reversed by re-adding a writable
  structure store; doing so would resurrect the duplication and the un-RBAC'd CMS.
- The server can no longer assemble drawers (structure lives in a frontend module),
  so the merge MUST stay client-side unless a backend manifest copy is introduced —
  which this ADR explicitly rejects to avoid a second source-of-truth.
- `data/page_status.json` shrinks but stays backward-compatible: a legacy
  full-CMS file is read for its `pages[].status` only (no error, no forced rewrite),
  and on rollback the restored `_migrate_navigation_schema` self-heals a
  route→status-only file back to the legacy drawers shape (from code defaults, not
  the renamed ids — exact pre-change menu requires restoring the file from git).
- No DB, queue, or cache is involved; rollback is a code revert plus optional
  `git checkout` of the data file.
