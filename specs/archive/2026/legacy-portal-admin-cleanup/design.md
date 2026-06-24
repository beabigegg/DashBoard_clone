# Design: legacy-portal-admin-cleanup

## Summary
Post `nav-config-to-code` (ADR 0012, `docs/adr/0012-navigation-source-of-truth-code-manifest.md`),
navigation *structure* lives in the frontend `navigationManifest.js` and the backend no
longer owns a drawers source. The legacy server-rendered home `templates/portal.html`
iterates a `drawers` list, but `portal_index()` (`app.py:1055-1060`) now feeds it the
route→status dict returned by `get_navigation_config()` (`page_registry.py:205-217`) — so the
non-SPA (`PORTAL_SPA_ENABLED=false`) branch renders degraded and is unreachable in default
config. This change removes that dead else-branch so `portal_index` *always* redirects to the
SPA (`portal_shell_page`), deletes `templates/portal.html`, and deletes the tests that
exercised the removed render path. It is a capability reduction of an already-broken,
non-default state with no user-visible change in the default (SPA-on) deployment. No backend
navigation-structure source is reintroduced (ADR 0012 forbids it). The `PORTAL_SPA_ENABLED`
flag is **kept** as a modernization/status signal; only its portal-rendering role is dropped.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| portal home route | `src/mes_dashboard/app.py` (`portal_index`, L1055-1060) | remove non-SPA else-branch; route unconditionally `redirect(url_for("portal_shell_page"))`. Keep route name `portal_index`. |
| legacy home template | `src/mes_dashboard/templates/portal.html` | DELETE (only consumer was the removed branch). |
| status payload | `src/mes_dashboard/app.py` (L1048) | UNCHANGED — `portal_spa_enabled` key preserved. |
| flag resolution | `src/mes_dashboard/app.py` (L262-272, L763) | UNCHANGED — `_resolve_portal_spa_enabled` + config wiring stay. |
| modernization policy | `src/mes_dashboard/core/modernization_policy.py` (L114) | UNCHANGED — `should_apply_canonical_redirect()` still reads the flag. |
| error/admin templates | `templates/{404,403,500}.html`, `templates/admin/pages.html` | UNCHANGED — `url_for('portal_index')` must still resolve (route name kept). |
| admin-pages CSS | `frontend/src/admin-pages/style.css` (~L192-268) | remove orphaned drawer-era rules (dead since `DrawerManagementPanel.vue` deletion). |
| admin-pages a11y | `frontend/src/admin-pages/{App.vue, components/PagesManagementPanel.vue}` | add `aria-pressed` to status toggle; `role="alert"`/`aria-live` to load-error panel. |
| backend render tests | `tests/test_template_integration.py`, `tests/test_portal_shell_routes.py`, `tests/test_hold_routes.py`, `tests/test_yield_alert_shell_coverage.py` | DELETE the render-branch tests / `PORTAL_SPA_ENABLED=false` *render* cases (see Test Impact). |
| route-name pin | `tests/test_app_factory.py` | strengthen `test_routes_registered` to assert `/` registers under name `portal_index`. |

## Key Decisions
- **Decision: `portal_index` always serves the SPA; delete the else-branch and `portal.html`.**
  Rationale: the else-branch is already broken (status dict passed as `drawers=`) and structure
  cannot be reassembled server-side post ADR 0012. → Rejected alt: *repair the non-SPA render by
  re-deriving drawers in the backend* — reintroduces a second navigation source-of-truth, which
  ADR 0012 explicitly rejects (resurrects the un-RBAC'd CMS + 3-way duplication). → Rejected alt:
  *keep portal.html as an empty/static stub* — dead template, no consumer, invites drift.
- **Decision: KEEP `PORTAL_SPA_ENABLED` (flag disposition).** After this change the flag no longer
  gates portal *rendering* (`portal_index` ignores it), but it retains live non-portal consumers:
  `modernization_policy.should_apply_canonical_redirect()` (canonical-redirect gate) and the status
  payload `portal_spa_enabled` key. It remains a modernization-tracking/status signal. → Rejected
  alt: *remove the flag* — would orphan those consumers and **promote this to an env-contract change**
  (`contracts/env/env-contract.md` + `env.schema.json` + `.env.example` edits and re-triggered
  contract tests), expanding scope beyond a Tier-3 cleanup. Not recommended.
- **Decision: default-behaviour parity is real, not assumed.** `config/settings.py:79` sets the
  flag default to `True` (SPA-on); the `app.config.get(..., False)` fallbacks are belt-and-suspenders.
  So removing the else-branch is a no-op in every default deployment — AC-1 "no user-visible change"
  holds. (Note: the change-request named a `modernization_policy.is_portal_spa_enabled` function;
  the actual consumer is `should_apply_canonical_redirect()` reading the config flag directly. No
  named `is_portal_spa_enabled` symbol exists — downstream agents should target the real call site.)

## Migration / Rollback
Pure code change. No DB / queue / cache / migration. Cutover: edit `portal_index` to drop the
else-branch, delete `portal.html`, delete the render tests, add the route-name pin. The
`PORTAL_SPA_ENABLED` env var, `config/settings.py` default, `env-contract.md`, and `env.schema.json`
are untouched. Rollback is a git revert of the same commit (restores `portal.html` and the
else-branch together — they must move as a unit so the template and its only caller never diverge).
No data-file or runbook step. Modernization manifests under `docs/migration/` are **not** touched:
`portal.html` is the legacy home, not a tracked report page (asset-readiness / route-scope matrices
key on report routes, not the `/` shell). CER-001 stays `pending` and unused — no manifest read was
required to reach this conclusion.

## Open Risks
- **Test Impact (precise blast radius).** Delete only the cases that *render* `portal.html`:
  `test_template_integration.py::TestTemplateIntegration::test_portal_includes_base_scripts`,
  `TestPortalDynamicDrawerRendering` (both tests, L102-203, patch the obsolete drawers-list shape),
  and `TestToastCSSIntegration::test_portal_includes_toast_css`. In `test_portal_shell_routes.py`,
  `test_hold_routes.py`, `test_yield_alert_shell_coverage.py` remove the `PORTAL_SPA_ENABLED=false`
  *render* branches. **Keep** `test_app_factory.py::test_portal_spa_flag_default_enabled` /
  `test_portal_spa_flag_disabled_via_env` / `test_portal_spa_flag_enabled_via_env` — they assert flag
  *resolution*, not rendering, and the flag survives. Deletions are deliberate (not skip/xfail).
- **`portal_index` route-name is load-bearing.** `url_for('portal_index')` is referenced by
  `404.html`, `403.html`, `500.html`, and `admin/pages.html`. Renaming the function would 500 those
  error pages; the new route-name pin in `test_app_factory.py` is the tripwire.
- **`admin/pages.html` still contains drawer-CRUD JS** (`#drawers-tbody`, `/admin/api/drawers`,
  L315-666). That is out of scope here (and likely already dead post ADR 0012 drawer-CRUD removal),
  but flagged so the implementation-planner does not assume `admin/pages.html` is clean — only its
  `url_for('portal_index')` back-link is in scope for this change.
