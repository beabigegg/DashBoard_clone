---
change-id: nav-config-to-code
schema-version: 0.1.0
last-changed: 2026-06-24
---

# Implementation Plan: nav-config-to-code

## Objective

Relocate the navigation **structure** source-of-truth (drawer id/name/order/admin_only,
page→drawer assignment, page order, page display name) from the runtime CMS
(`data/page_status.json` + admin drawer endpoints) into a frontend code manifest, and
shrink the only runtime-writable concern to a per-page `released`/`dev` `status`. After
this change the structure×status merge happens fully client-side; `/api/portal/navigation`
becomes a status feed; drawer CRUD and the name/drawer_id/order mutation path are removed.
The non-admin rendered menu must stay structurally identical (AC-1) sourced entirely from
the new manifest. See `design.md §Summary` and `change-request.md` AC-1..AC-4.

## Execution Scope

> **Sequencing is strict: `backend-engineer` runs FIRST, then `frontend-engineer`.**
> Rationale: the frontend consumes (a) the inverted `GET /api/portal/navigation` status-feed
> shape and (b) the data-shape **§3.11b** navigation-manifest contract that the backend
> establishes in this change. Do not start frontend work until the backend contract edits
> (incl. data-shape §3.11b) and the regenerated `get_portal_navigation.json` sample are in.

### In Scope
- Backend: remove drawer CRUD + the name/drawer_id/order write path; slim `GET /api/pages`
  and `PUT /api/pages/<route>` to status-only; invert `portal_navigation_config` (app.py
  L1108) to a status feed; shrink `page_registry` + `data/page_status.json` to
  `{api_public, statuses}` with legacy full-CMS back-compat read; backend tests.
- Backend (contracts): apply the API + data-shape + inventory + CHANGELOG edits specified by
  `design.md` and `change-classification.md §Required Contracts` (author data-shape **§3.11b**
  manifest contract); regen **both** `contracts/openapi.json` and `contracts/api/openapi.json`;
  retire 4 drawer samples + their `response-samples.json` entries; reslim `get_admin_pages.json`;
  regen `get_portal_navigation.json`.
- Frontend: new `navigationManifest.js`; rewire `navigationState.js`/`App.vue`/`router.js`
  to merge `(manifest, statusMap)` client-side; delete `DrawerManagementPanel`; slim
  `admin-pages/` to status-toggle-only (join names from manifest); frontend tests.

### Out of Scope (non-goals — do NOT do these)
- **No per-user/role RBAC.** Visibility stays binary admin vs non-admin (`canViewPage`
  unchanged). See `current-behavior.md §Visibility semantics`.
- **No change to which routes are mountable.** `nativeModuleRegistry.js` and `routeContracts.js`
  are **unchanged**; the manifest must NOT duplicate the mount gate or policy meta
  (`design.md` Key Decision 1).
- **No menu redesign.** Display names and page memberships are preserved **verbatim**
  (`current-behavior.md §Current live menu`); only internal drawer ids are cleaned up.
- **No env / deploy change.** No new flags, no worker/gunicorn env, no new workflow file
  (`ci-gates.md §Workflow Changes Applied`).
- **No DB / Redis / RQ / spool / cache touch.** No parquet `rm`, no namespace edits.
- Do NOT opportunistically refactor `app.py`, `routeContracts.js`, or any file outside the
  File-Level Plan.

## Hard Constraints (READ BEFORE TOUCHING CODE — silent-failure traps)

1. **AC-1 menu parity is a CLIENT-SIDE diff, not a backend signal.** Correctness lives in
   `buildDynamicNavigationState(manifest, statusMap)` output vs the captured baseline in
   `current-behavior.md §Current live menu`. A wrong order/drawerId/displayName in the manifest
   is **silent at the backend** — there is no server validation of structure after this change.
   Frontend tests MUST assert the built JS nav tree for admin AND non-admin
   (`test-plan.md §Notes`, `design.md §Open Risks`).
2. **PRESERVE `api_public` in `data/page_status.json`.** It is read by
   `page_registry.is_api_public()` (page_registry.py L480-494) and gates a **site-wide auth
   bypass**. The shrink target is `{api_public, statuses}` — dropping `api_public` silently
   disables that gate. `tests/test_page_registry.py::TestIsApiPublic::test_api_public_key_preserved_after_shrink`
   is the tripwire (`design.md §Open Risks`).
3. **The real nav surface is `GET /api/portal/navigation` (`app.py::portal_navigation_config`,
   ~L1108) — NOT `GET /api/drawers`.** This is the AC-1 surface that must be inverted to a
   status feed. `GET /api/drawers` is being deleted entirely (`design.md §Affected Components`,
   `current-behavior.md` runtime-endpoints note). CER-003 (app.py) is APPROVED.
4. **Regen BOTH openapi files.** `contracts/openapi.json` AND `contracts/api/openapi.json` must
   be drawer-path-free after edit, or the `openapi-sync` gate blocks merge
   (`ci-gates.md §openapi-sync`). Retire all 4 drawer samples, reslim `get_admin_pages.json`,
   regen `get_portal_navigation.json` to the `{statuses:…}` shape.
5. **Drawer-id rename + explicit distinct orders, names/memberships verbatim.**
   `drawer-2`→`history-reports`, `drawer`→`query-tools`, `drawer-3`→`trace-tools`; keep
   `reports`/`dev-tools`/`eap-analysis`; **drop empty `test` drawer**. Assign distinct integer
   drawer orders 1..6 (reports=1, history-reports=2, query-tools=3, trace-tools=4, dev-tools=5,
   eap-analysis=6) and within trace-tools page orders `/query-tool`=1, `/mid-section-defect`=2,
   `/material-trace`=3. Display names + page memberships copied **verbatim** from the
   `current-behavior.md` table. Standalone routes (`/`, `/wip-detail`, `/hold-detail`) stay
   outside any drawer (already `STANDALONE_DRILLDOWN_ROUTES` in `navigationState.js`).
   `defaultStatus:'dev'` on `/admin/dashboard` only. See `design.md` Key Decisions 4–5.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | contracts (API) | Remove the 4 drawer rows + slim the `GET/PUT /api/pages` rows in `contracts/api/api-contract.md` (L222-226) and `contracts/api/api-inventory.md`; reshape the `GET /api/portal/navigation` row (L235) to the status feed. Per `change-classification.md §Required Contracts` + `design.md §Affected Components`. | backend-engineer |
| IP-2 | contracts (data) | Author data-shape **§3.11b** navigation-manifest contract + the shrunk writable-store (`{api_public, statuses}`) shape + slimmed `GET /api/pages` response in `contracts/data/data-shape-contract.md`. | backend-engineer |
| IP-3 | contracts (CHANGELOG + openapi) | Breaking removal entry in `contracts/CHANGELOG.md` (new `api` version, `### Removed`); regen **both** `contracts/openapi.json` and `contracts/api/openapi.json`. | backend-engineer |
| IP-4 | contract samples | Retire `get/post/put/delete _admin_drawers*.json` (disk + `response-samples.json` entries via `capture_samples.py`); reslim `get_admin_pages.json`; regen `get_portal_navigation.json`. | backend-engineer |
| IP-5 | backend nav endpoint | Invert `app.py::portal_navigation_config` (~L1108) to emit `{statuses, is_admin, admin_user, admin_links, features, diagnostics}` — drop `drawers`/names/order (`design.md` Key Decision 2). | backend-engineer |
| IP-6 | backend admin API | In `admin_routes.py`: delete `api_get_drawers`/`api_create_drawer`/`api_update_drawer`/`api_delete_drawer` (L1381-1454) + their imports (L42); `api_get_pages` (L1374-1376) → `{pages:[{route,status}]}`; `PUT /api/pages/<route>` handler (api_set_page_status) accepts only `status`, rejects name/drawer_id/order. | backend-engineer |
| IP-7 | backend page service | In `page_registry.py`: drop `get_all_drawers`/`create_drawer`/`update_drawer`/`delete_drawer` (L339-436) + `_migrate_navigation_schema`/drawer helpers; `set_page_status` (L276-326) → status-only; `get_all_pages` → route+status; read path fails safe on missing/legacy full-CMS store; `get_navigation_config` reslimmed. Preserve `is_api_public`. | backend-engineer |
| IP-8 | writable store | Shrink `data/page_status.json` to `{api_public, statuses:{route:status}}` (only `/admin/dashboard:'dev'` non-default; others omittable). | backend-engineer |
| IP-9 | backend tests | `tests/test_admin_routes.py`, `tests/test_page_registry.py`, `tests/contract/*` per `test-plan.md §AC-2/3/4/6/7/8` + `§Test Update Contract`. | backend-engineer |
| IP-10 | frontend manifest (NEW) | Create `frontend/src/portal-shell/navigationManifest.js` per data-shape §3.11b + `current-behavior.md` layout (drawers[], route→{drawerId,order,displayName}, defaultStatus). | frontend-engineer |
| IP-11 | frontend merge | `navigationState.js`: `buildDynamicNavigationState`/`normalizeNavigationDrawers` take `(manifest, statusMap)` instead of pre-merged backend `drawers`; apply existing `canViewPage`/`admin_only`/empty-drawer-drop/sort rules unchanged. | frontend-engineer |
| IP-12 | frontend bootstrap + router | `App.vue::loadNavigation()` reads `statuses` from `/api/portal/navigation`, passes `(manifest, statusMap)` to `syncNavigationRoutes`; `router.js::syncNavigationRoutes` (L56-98) signature follows. | frontend-engineer |
| IP-13 | frontend admin UI | Delete `admin-pages/components/DrawerManagementPanel.vue`; remove drawer-assignment select from `PagesManagementPanel.vue`; `admin-pages/App.vue` status-toggle only, join page names from the manifest. | frontend-engineer |
| IP-14 | frontend tests | `frontend/tests/legacy/portal-shell-navigation.test.js`, `frontend/src/portal-shell/__tests__/navigationManifest.test.js`, `frontend/tests/playwright/{admin-pages,portal-shell-login}.spec.ts` per `test-plan.md §AC-1/2/3/5`. | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | §Affected Components (table) | per-file nature-of-change for IP-5..IP-13 |
| design.md | Key Decisions 1–5; §Migration / Rollback | manifest schema, status-feed shape, rename/order rules, back-compat read, rollback |
| change-classification.md | §Required Contracts; §Inferred Acceptance Criteria (AC-1..AC-8) | exact contract edits + acceptance scope |
| current-behavior.md | §Current live menu (table) + §Visibility semantics | verbatim manifest source-of-truth (AC-5) + AC-1 baseline |
| test-plan.md | AC→test mapping; §Test Update Contract; §Notes | tests to write/retire + AC-1 JS-object-diff warning |
| ci-gates.md | Required Gates table; §openapi-sync; §response-shape-validate | verification commands + sample-retire ordering |
| contracts/api/api-contract.md | L222-226 (drawer/pages rows), L235 (portal/navigation row) | API edit targets |
| contracts/data/data-shape-contract.md | new §3.11b (author) + writable-store / GET-pages shapes | data-shape edit targets |
| context-manifest.md | §Approved Expansions (CER-001/002/003 approved) | read-scope authorization |

## File-Level Plan

### Backend engineer (runs FIRST)

| path | action | notes (ref) |
|---|---|---|
| `contracts/api/api-contract.md` | edit | Remove drawer rows L223-226; reshape `GET /api/pages` (L222) to slim `{pages:[{route,status}]}` + `PUT /api/pages/<route>` body to status-only; reshape `GET /api/portal/navigation` (L235) to status feed. `design.md §Affected Components`. Follow §Schema Authoring Rules; bare-identifier schema cells. |
| `contracts/api/api-inventory.md` | edit | Drop the 4 drawer endpoints. |
| `contracts/data/data-shape-contract.md` | edit | **Author §3.11b** navigation-manifest shape; add shrunk writable-store `{api_public, statuses}` + slimmed `GET /api/pages` shapes. `change-classification.md §Required Contracts` (Data shape). |
| `contracts/business/business-rules.md` | edit (conditional) | Only a wording/pointer touch if `released`/`dev` visibility wording moves; likely no-op (`change-classification.md` §Required Contracts → Business: conditional). Skip if behavior-identical. |
| `contracts/CHANGELOG.md` | edit | New `api` version, `### Removed`: drawer CRUD + `GET /api/drawers` + name/drawer_id/order on `PUT /api/pages`. Entry goes here ONLY. |
| `contracts/openapi.json` | regen | Must be drawer-path-free (gate `openapi-sync`). |
| `contracts/api/openapi.json` | regen | Same; both files regenerated in this PR. |
| `tests/contract/samples/get_admin_drawers.json` | delete | Retire (`ci-gates.md §response-shape-validate`). |
| `tests/contract/samples/post_admin_drawers.json` | delete | Retire. |
| `tests/contract/samples/put_admin_drawers_id.json` | delete | Retire. |
| `tests/contract/samples/delete_admin_drawers_id.json` | delete | Retire. |
| `tests/contract/response-samples.json` | edit | Remove the 4 drawer entries (via `capture_samples.py`; CER-002 approved). |
| `tests/contract/samples/get_admin_pages.json` | regen | Reslim to `{pages:[{route,status}]}`. |
| `tests/contract/samples/get_portal_navigation.json` | regen | Regen to `{statuses:{route:status},…}` (no drawers). |
| `src/mes_dashboard/app.py` | edit | `portal_navigation_config` (~L1108): emit `statuses` map; stop emitting `drawers`/names/order; keep `is_admin`/`admin_user`/`admin_links`/`features`/`diagnostics`. CER-003 approved. Decide diagnostics-of-structure removal (log-only, low risk — `design.md §Open Risks`). |
| `src/mes_dashboard/routes/admin_routes.py` | edit | Delete `api_get_drawers` (L1381-1383), `api_create_drawer` (L1388-1405), `api_update_drawer` (L1410-1437), `api_delete_drawer` (L1442-1454); trim L42 import to `{get_all_pages, get_page_status, set_page_status}`; `api_get_pages` (L1374-1376) → slim; `PUT /api/pages/<route>` handler → status-only, reject name/drawer_id/order. |
| `src/mes_dashboard/services/page_registry.py` | edit | Drop `get_all_drawers`/`create_drawer`/`update_drawer`/`delete_drawer` (L339-436), `_migrate_navigation_schema` (L139-169) + drawer helpers + `DrawerError`/`DrawerNotFoundError`/`DrawerConflictError` once unused; `set_page_status` (L276-326) status-only; `get_all_pages` (L329-336) → route+status; `get_navigation_config` (L439-477) reslimmed; `_load` fails safe on missing/legacy full-CMS. **Keep `is_api_public` (L480-494).** |
| `data/page_status.json` | edit | Shrink to `{api_public, statuses:{route:status}}`; only `/admin/dashboard:'dev'` non-default. |
| `tests/test_admin_routes.py` | edit | Per `test-plan.md §AC-3/7` + §Test Update Contract (drawer-404 replacements; field-rejection tests). |
| `tests/test_page_registry.py` | edit | Per `test-plan.md §AC-2/6` (delete `TestDrawerCrud`/`TestSchemaMigration`; add `TestShrunkStoreBackCompat`; `TestIsApiPublic` preservation). Use a real temp-file fixture for back-compat (`test-plan.md §Notes`). |
| `tests/contract/test_schema_coverage.py` | edit | Decrement endpoint-count pin by 4 (`test-plan.md §AC-4/8`). |
| `tests/contract/test_openapi_schema_resolution.py` | edit | Decrement operation-count pin by 4 (`test-plan.md §Test Update Contract`). |

### Frontend engineer (runs AFTER backend)

| path | action | notes (ref) |
|---|---|---|
| `frontend/src/portal-shell/navigationManifest.js` | create | Structure-only single source of truth per data-shape §3.11b; reproduce `current-behavior.md` layout 1:1 (renamed ids, distinct orders, names/memberships verbatim, `defaultStatus:'dev'` on `/admin/dashboard`). Must NOT duplicate `nativeModuleRegistry`/`routeContracts` (`design.md` Key Decision 1). |
| `frontend/src/portal-shell/navigationState.js` | edit | `buildDynamicNavigationState`/`normalizeNavigationDrawers` (L31-166) take `(manifest, statusMap)`; keep `STANDALONE_DRILLDOWN_ROUTES`, `canViewPage`, sort, empty-drawer-drop unchanged (`design.md §Affected Components`). |
| `frontend/src/portal-shell/App.vue` | edit | `loadNavigation()` reads `statuses` from `/api/portal/navigation`; pass `(manifest, statusMap)` to `syncNavigationRoutes`. |
| `frontend/src/portal-shell/router.js` | edit | `syncNavigationRoutes` (L56-98) signature follows `navigationState`; otherwise unchanged. |
| `frontend/src/portal-shell/nativeModuleRegistry.js` | unchanged | Mount gate — do not edit (non-goal). |
| `frontend/src/portal-shell/routeContracts.js` | unchanged | Policy meta — do not edit (non-goal). |
| `frontend/src/admin-pages/components/DrawerManagementPanel.vue` | delete | Drawer management retired (`design.md §Affected Components`). |
| `frontend/src/admin-pages/components/PagesManagementPanel.vue` | edit | Remove drawer-assignment select; status-toggle only; render page name joined from manifest. |
| `frontend/src/admin-pages/App.vue` | edit | Drop `DrawerManagementPanel` usage; status-toggle-only flow; join names from manifest + `GET /api/pages` status map. |
| `frontend/src/portal-shell/__tests__/navigationManifest.test.js` | create | `test-plan.md §AC-5` (routes-exist-in-registry; defaultStatus dev only on admin/dashboard). |
| `frontend/tests/legacy/portal-shell-navigation.test.js` | edit | Extend with manifest nav-tree parity (admin + non-admin) + order/rename/verbatim invariants (`test-plan.md §AC-1/5`). Assert built JS object vs `current-behavior.md` baseline. |
| `frontend/tests/playwright/admin-pages.spec.ts` | edit | Status-toggle round-trip; `DrawerManagementPanel` absent; delete drawer-creation/MOCK_DRAWERS tests (`test-plan.md §AC-2/3` + §Test Update Contract). |
| `frontend/tests/playwright/portal-shell-login.spec.ts` | edit | `test_non_admin_sidebar_drawers_match_baseline` (`test-plan.md §AC-1`). |

## Contract Updates

- **API:** Remove `GET/POST/PUT/DELETE /api/drawers`; slim `GET /api/pages` to
  `{pages:[{route,status}]}`; restrict `PUT /api/pages/<route>` body to `status`; reshape
  `GET /api/portal/navigation` to a status feed (`{statuses,…}`, no `drawers`). Update
  `api-contract.md` (L222-226, L235) + `api-inventory.md`; regen both `openapi.json`.
  Breaking `### Removed` entry in `contracts/CHANGELOG.md`. (Owner: backend-engineer.)
- **CSS/UI:** None (non-goal; no new visual design — `change-classification.md`).
- **Env:** None (non-goal).
- **Data shape:** Author data-shape **§3.11b** (navigation manifest) + shrunk writable-store
  `{api_public, statuses}` + slimmed `GET /api/pages` shape in `data-shape-contract.md`.
  (Owner: backend-engineer.)
- **Business logic:** Conditional / likely no-op — touch `business-rules.md` only if
  `released`/`dev` wording must move; behavior is unchanged (`change-classification.md`).
- **CI/CD:** No new workflow/gate. Existing gates must stay green after sample retire/regen;
  modernization manifests need **no structural edit** (`/admin/pages` stays a route entry —
  `design.md §Affected Components`).

## Test Execution Plan

Per `test-plan.md` (AC→test mapping) and `ci-gates.md` (Required Gates). Each engineer runs the
bounded ladder for its scope: first `cdd-kit test select nav-config-to-code --json`, then
`cdd-kit test run nav-config-to-code --phase <phase> --command "<cmd>"` for **collect, targeted,
changed-area, contract** — declare the conditional `contract` phase with `--required-phases` on
the first run. This produces `test-evidence.yml`; the gate validates that artifact. Full ladder
and rationale live in `test-plan.md` / `references/sdd-tdd-policy.md` — not restated here.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `frontend/tests/legacy/portal-shell-navigation.test.js` | built `buildDynamicNavigationState(manifest, statusMap)` tree (drawers/order/name/visible-set) matches `current-behavior.md` baseline for admin AND non-admin |
| AC-1 | `frontend/tests/playwright/portal-shell-login.spec.ts` | rendered non-admin sidebar drawer/page structure matches baseline |
| AC-2 | `tests/test_page_registry.py` (`TestSetPageStatus`) | status set on shrunk store persists + reflected in `get_all_pages` |
| AC-2 | `frontend/tests/playwright/admin-pages.spec.ts` | `released`→`dev` toggle round-trips and persists |
| AC-3 | `tests/test_admin_routes.py` | `GET/POST/PUT/DELETE /api/drawers` → 404; `PUT /api/pages` with name/drawer_id/order → rejected |
| AC-3 | `frontend/tests/playwright/admin-pages.spec.ts` | `DrawerManagementPanel` absent from DOM |
| AC-4/8 | `tests/contract/test_schema_coverage.py`, `test_manifest_completeness.py`, `test_openapi_schema_resolution.py` | endpoint/operation pins (-4) pass; drawer samples absent from manifest; pages sample present; no unresolved refs |
| AC-5 | `frontend/src/portal-shell/__tests__/navigationManifest.test.js` | every manifest route exists in `nativeModuleRegistry`; `defaultStatus:'dev'` only on `/admin/dashboard` |
| AC-5 | `frontend/tests/legacy/portal-shell-navigation.test.js` | clean drawer ids; no `test` drawer; display names + memberships verbatim |
| AC-6 | `tests/test_page_registry.py` (`TestShrunkStoreBackCompat`, `TestIsApiPublic`) | legacy full-CMS file yields correct statuses; missing file → `released`; `defaultStatus:'dev'` hides `/admin/dashboard`; `api_public` key preserved |
| AC-7 | `tests/test_admin_routes.py` | removed routes 404/405 + non-status fields rejected, all under `@admin_required` |
| AC-8 | `cdd-kit validate --contracts` / `--openapi` | drawer samples retired; both `openapi.json` drawer-path-free |

## Handoff Constraints

- **Strict order: `backend-engineer` completes (incl. contracts + data-shape §3.11b +
  regenerated `get_portal_navigation.json`) BEFORE `frontend-engineer` starts.** The frontend
  consumes the status-feed shape and the §3.11b manifest contract the backend establishes.
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow
  the Source Artifact Pointers.
- Read scope is `context-manifest.md §Allowed Paths` + approved expansions (CER-001/002/003 all
  APPROVED). Need a path not listed → file a Context Expansion Request and stop.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the File-Level Plan; `nativeModuleRegistry.js` and `routeContracts.js`
  are explicitly out of scope.
- After any endpoint-table or schema edit, **regenerate both `openapi.json` files** and rerun
  `cdd-kit validate --contracts` (requires `jsonschema` installed) before declaring done.

## Known Risks

- **AC-1 silent regression (highest).** The merge is now client-side; a manifest
  order/drawerId/displayName typo breaks the rendered menu with **no backend signal**. Mitigated
  only by the `buildDynamicNavigationState` object-diff tests for admin + non-admin
  (`test-plan.md §Notes`, `design.md §Open Risks`). Treat the parity test as the gate, not the
  endpoint shape.
- **`api_public` drop = site-wide auth-bypass regression.** The shrink must keep `api_public`
  in `data/page_status.json` and `is_api_public()` intact (page_registry.py L480-494). Tripwire:
  `TestIsApiPublic::test_api_public_key_preserved_after_shrink`.
- **`db_scan` consumer.** `data/page_status.json` `db_scan` is read by a tools script unrelated to
  nav (`design.md §Open Risks`). Confirm whether the shrink drops it safely or must retain it;
  do not assume removable without checking the tools-script reader.
- **Two openapi files + sample lockstep.** Forgetting `contracts/api/openapi.json` (vs only
  `contracts/openapi.json`) or leaving a stale drawer entry in `response-samples.json` fails
  `openapi-sync` / `response-shape-validate`. Retire all 4 drawer samples + regen pages/navigation
  samples in the same change.
- **Rollback self-heal nuance.** A shrunk `page_status.json` self-heals to `DEFAULT_DRAWERS` ids
  (not the renamed ids) on first post-rollback read; exact pre-change menu requires
  `git checkout data/page_status.json` (`design.md §Migration / Rollback`, `ci-gates.md §Rollback`).
  No code action needed now — note for the rollback runbook only.
- **No standalone contract-reviewer edit-spec artifact exists in the change dir.** The contract
  edits (IP-1..IP-4) are fully specified by `design.md §Affected Components` + §Migration/Rollback
  and `change-classification.md §Required Contracts`; the backend-engineer applies them from those
  sources. Not a blocker — the spec is complete across those artifacts.
- **`diagnostics.contract_mismatch_routes`** in `portal_navigation_config` validated server-assembled
  structure that no longer exists; it becomes vacuous. Drop it or move an equivalent check into the
  frontend manifest-vs-registry test (covered by `navigationManifest.test.js`). Log-only, low risk
  (`design.md §Open Risks`, `test-plan.md §Out of Scope`).
