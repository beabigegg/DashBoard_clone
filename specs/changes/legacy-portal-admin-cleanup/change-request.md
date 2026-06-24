# Change Request

## Original Request

Clean up the three non-blocking follow-ups recorded in the archived `nav-config-to-code` change (`specs/archive/2026/nav-config-to-code/regression-report.md`). Affected surface: the legacy non-SPA portal render path (backend) + the admin-pages frontend.

**Item 1 — Deprecate the broken legacy non-SPA portal render path.**
`portal_index()` (the `/` route, `src/mes_dashboard/app.py` ~L1056) serves the SPA when `PORTAL_SPA_ENABLED` is true (the DEFAULT) but otherwise does `render_template('portal.html', drawers=get_navigation_config())`. After nav-config-to-code, `get_navigation_config()` returns a status dict (route→status), NOT a drawers list, so `portal.html` (which iterates `drawers`) renders degraded. The non-SPA portal can no longer obtain nav structure (it moved to the frontend `navigationManifest.js`) — **do NOT re-introduce a backend structure source**. Decision (spec-architect): deprecate/remove the non-SPA `portal.html` render branch so `portal_index` always serves the SPA; remove `src/mes_dashboard/templates/portal.html` and the tests exercising the `PORTAL_SPA_ENABLED=false` non-SPA render (e.g. `tests/test_template_integration.py` portal renders, and `PORTAL_SPA_ENABLED=false` branches in `tests/test_portal_shell_routes.py` / `test_hold_routes.py` / `test_yield_alert_shell_coverage.py`).
**HARD CONSTRAINTS:** (a) KEEP the `portal_index` route NAME — referenced by `src/mes_dashboard/templates/{404,403,500}.html` + `admin/pages.html` via `url_for('portal_index')`; (b) `PORTAL_SPA_ENABLED` has OTHER consumers — `core/modernization_policy.py:114` (`is_portal_spa_enabled`), the status payload at `app.py:1048` (`portal_spa_enabled` key), and tests — assess whether the flag stays (likely yes) or is simplified; do not blindly delete it.

**Item 2 — Remove orphaned admin-pages CSS.**
`frontend/src/admin-pages/style.css` (~L192-268) still has drawer-era rules (`.input`, `.order-input`, `.drawer-create`, `.checkbox-label`, `.action-btn` + variants, `.actions-cell`) left over from the deleted `DrawerManagementPanel.vue` — dead CSS (still `.theme-admin-pages`-scoped so `css:check` passes). Remove them.

**Item 3 — admin-pages a11y.**
In `frontend/src/admin-pages/` (`App.vue` / `components/PagesManagementPanel.vue`): add `aria-pressed` to the Released/Dev status-toggle button (reflecting current state), and `role="alert"` (or `aria-live`) to the load-error panel so it is announced.

**Success criteria (confirmed):**
- AC-1: Full test suite + CI green with the legacy non-SPA `portal.html` render path removed (or proven unreachable); `portal_index` keeps serving the SPA by default with no user-visible change.
- AC-2: `portal_index` route name preserved (the `url_for('portal_index')` references in 404/403/500/admin templates still resolve); `PORTAL_SPA_ENABLED`'s non-portal consumers (`modernization_policy`, status payload) remain correct.
- AC-3: No orphaned drawer-era CSS rules remain in `admin-pages/style.css`; `css:check` passes.
- AC-4: admin status-toggle button exposes `aria-pressed`; the load-error panel exposes `role="alert"`.

## Business / User Goal

## Non-goals
- No change to the default (SPA) navigation behavior.
- No re-introduction of a backend navigation-structure source.
- No new feature; pure cleanup/deprecation of artifacts left by nav-config-to-code.

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
