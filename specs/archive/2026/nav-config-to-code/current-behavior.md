# Current Behavior (baseline / regression anchor)

Captured from live source at change start. This is the AC-5 migration source-of-truth and the AC-1 regression baseline. The code manifest must reproduce the **rendered** layout below 1:1.

## Today's 3-layer navigation config (the duplication being collapsed)
| Layer | File | Owns |
|---|---|---|
| Mountable route → component+CSS | `frontend/src/portal-shell/nativeModuleRegistry.js` | hard gate on what can mount (native dynamic `import()`) |
| Per-route policy meta | `frontend/src/portal-shell/routeContracts.js` | renderMode / routeId / visibilityPolicy / scope / compatibilityPolicy / owner / title |
| Menu placement + visibility | `data/page_status.json` (+ admin API, consumed by `navigationState.js`) | drawer grouping, order, display name, `released`/`dev` status |

## Runtime endpoints today (`src/mes_dashboard/routes/admin_routes.py`, all `@admin_required`)
- `GET /api/pages` (L1372) → `get_all_pages()` — full page CMS list
- `PUT /api/pages/<route>` (L1457) → `set_page_status(route, status, name=, drawer_id=, order=)` — mutates status **and** name/drawer_id/order
- `GET /api/drawers` (L1379) → `get_all_drawers()`
- `POST /api/drawers` (L1386) → `create_drawer(name, order, admin_only)`
- `PUT /api/drawers/<id>` (L1408) → `update_drawer(...)`
- `DELETE /api/drawers/<id>` (L1440) → `delete_drawer(id)`
- Service owner: `src/mes_dashboard/services/page_registry.py` (CER-001 confirmed)

## Visibility semantics (`navigationState.js`)
- `canViewPage(status, isAdmin)`: admin sees all; non-admin sees only `status === 'released'`.
- Drawer `admin_only: true` → hidden from non-admins entirely.
- Empty drawers (no visible pages) are dropped (`normalizedPages.length === 0`).
- Sort: by `order` asc, then `name` `localeCompare` tiebreak (drawers and pages both).
- **No per-user/role RBAC** — visibility is binary admin vs non-admin only.

## Writable store shape today (`data/page_status.json`)
Top-level keys: `api_public` (bool), `db_scan` (object), `drawers` (array), `pages` (array). Target: shrink to a minimal `route → status` map; everything else moves to the code manifest.

## Current live menu (the migration target — reproduce exactly)
Drawers (effective order; `test` is empty → not rendered). **`id` rename is internal only — display `name` must be preserved unchanged.**

| current id | display name (preserve) | order | admin_only | suggested clean id |
|---|---|---|---|---|
| reports | 即時報表 | 1 | no | `reports` (keep) |
| drawer-2 | 歷史報表 | 2 | no | `history-reports` |
| drawer | 查詢工具 | 3 | no | `query-tools` |
| dev-tools | 開發工具 | 4 | **yes** | `dev-tools` (keep) |
| drawer-3 | 追溯工具 | 4 | no | `trace-tools` |
| eap-analysis | EAP | 5 | no | `eap-analysis` (keep) |
| test | test | 1 | no | **DROP (empty)** |

Pages per drawer (route · order · name · status):

- **即時報表**: `/wip-overview`·1·WIP 即時概況·released · `/hold-overview`·2·Hold 即時概況·released · `/resource`·4·設備即時概況·released · `/qc-gate`·6·QC-GATE 狀態·released
- **歷史報表**: `/hold-history`·3·Hold 歷史績效·released · `/resource-history`·5·設備歷史績效·released · `/downtime-analysis`·6·設備停機分析·released
- **查詢工具**: `/reject-history`·1·報廢歷史查詢·released · `/job-query`·2·設備維修查詢·released · `/production-history`·3·生產歷程查詢·released · `/yield-alert-center`·4·良率查詢·released · `/material-consumption`·6·原物料用量查詢·released
- **追溯工具**: `/query-tool`·2·批次追蹤工具·released · `/mid-section-defect`·3·製程不良追溯分析·released · `/material-trace`·3·原物料追溯查詢·released  ⚠ two pages share order 3 (name tiebreak)
- **開發工具** (admin-only): `/admin/pages`·1·頁面管理·released · `/admin/dashboard`·2·管理儀表板·**dev**
- **EAP**: `/eap-alarm`·1·EAP ALARM 分析·released

Non-menu / standalone routes (not in any drawer; `drawer_id: null`): `/` (首頁), `/wip-detail` (WIP 明細), `/hold-detail` (Hold 明細) — these are home + standalone drill-down (`STANDALONE_DRILLDOWN_ROUTES` in `navigationState.js`), independent of the drawer menu. The manifest must not lose them.

## Order-collision note (must be reproduced or made explicit)
- `dev-tools` and `trace-tools` both `order: 4` → current relative order is name-tiebreak-dependent. Recommend the manifest assign **explicit distinct integer orders** reproducing the current visual order to remove the ambiguity.
- Within 追溯工具, `/mid-section-defect` and `/material-trace` both `order: 3` → same; assign distinct orders.

## `/admin/dashboard` is the only `dev` page
20/21 pages are `released`; only `/admin/dashboard` is `dev`. This single live use of the status gate is the capability that stays runtime-configurable (AC-2).
