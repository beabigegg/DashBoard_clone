# Archive — legacy-portal-admin-cleanup

## Change Summary
Cleaned up the three non-blocking follow-ups left by the merged `nav-config-to-code` change: (1) deprecated the broken legacy non-SPA portal render path, (2) removed orphaned drawer-era CSS in admin-pages, (3) added admin-pages a11y attributes. Tier 3, low risk; no user-visible change to the default (SPA) experience.

## Final Behavior
- `portal_index()` (`/`) now **unconditionally** `redirect(url_for("portal_shell_page"))` — the broken `else: render_template('portal.html', drawers=get_navigation_config())` branch is gone and `src/mes_dashboard/templates/portal.html` is deleted. (After nav-config-to-code, `get_navigation_config()` returns a status dict not a drawers list, so that branch rendered degraded.)
- **Preserved**: the `portal_index` route NAME (used by `url_for` in 404/403/500 + admin/pages templates), `PORTAL_SPA_ENABLED` (now no longer gates portal rendering but stays for `modernization_policy.should_apply_canonical_redirect` + the status `portal_spa_enabled` key), and the flag wiring/status key unchanged.
- admin-pages: dead drawer-era CSS removed from `style.css`; the Released/Dev status toggle exposes `aria-pressed`; the load-error panel exposes `role="alert"`.

## Final Contracts Updated
- **None.** contract-reviewer verified: no API change (portal_index still 200; status `portal_spa_enabled` key preserved; `/api/portal/navigation` unchanged), no env change (`PORTAL_SPA_ENABLED` kept), no css-inventory change (dead-rule removal within the still-`.theme-admin-pages`-scoped file). Empty git diff on `contracts/env/*`.

## Final Tests Added / Updated
- Deleted (deliberate, not skip/xfail): the portal.html-rendering tests in `tests/test_template_integration.py` (`TestPortalDynamicDrawerRendering`, `test_portal_includes_base_scripts`, `TestToastCSSIntegration::test_portal_includes_toast_css`) + the `PORTAL_SPA_ENABLED=false` render tests in `tests/test_portal_shell_routes.py`, `tests/test_hold_routes.py`, `tests/test_yield_alert_shell_coverage.py`.
- Added to `tests/test_app_factory.py`: `/`→`portal_index` route-name pin; portal_index always redirects regardless of the flag; status payload exposes `portal_spa_enabled`; `portal.html` deleted; AST absence-proof for `portal.html`. Kept the flag-resolution tests.
- New frontend vitest: `frontend/src/admin-pages/__tests__/{PagesManagementPanel,App}.test.ts` (aria-pressed true/false; role=alert).
- Evidence: backend full suite **4881 passed, 0 failed**; frontend vitest 3/3; `css:check` + `vue-tsc` clean.

## Final CI/CD Gates
Per `ci-gates.md` — rides existing gates (no new): `unit-and-integration-tests`, `frontend-unit-tests`, `css:check`, `e2e-critical`, `released-pages-hardening`. PR #8 (DashBoard_clone) — all checks green; merged squash `b876da72`.

## Production Reality Findings
1. **Brief corrections by spec-architect**: there is no `is_portal_spa_enabled` symbol — the real flag consumer is `should_apply_canonical_redirect()` (`modernization_policy.py:114`); and `PORTAL_SPA_ENABLED` defaults **True** (`config/settings.py:79`), which is what makes AC-1 "no user-visible change" true (the removed branch is unreachable in default deployments).
2. **Full-suite run caught a straggler** (the promoted nav-config-to-code learning, re-validated): `test_portal_spa_flag_disabled_via_env` asserted on now-deleted `portal.html` content; updated to a redirect assertion. The bounded ladder alone would have missed it.
3. **Tier-floor scanner false-positive** (2nd CDD change in a row): matched incidental substrings `index`/`integration`/`route` (= `portal_index`, `test_template_integration.py`, route names) and demanded Tier 2; resolved with an audited `tier-floor-override` (genuinely Tier 3, contract-reviewer confirmed zero contract change).
4. **167-sample churn reverted** (re-validated learning): the full-suite run re-ran `test_capture_samples`; reverted to keep the diff tight.
5. Out-of-scope finding (spec-architect): the server template `templates/admin/pages.html` still carries dead drawer-CRUD JS (`#drawers-tbody`, `/admin/api/drawers`); left untouched (only its `url_for('portal_index')` back-link was in scope).

## Lessons Promoted to Standards
**None newly promoted** (contract-reviewer evidence-gated). The three workflow learnings this change re-validated — (a) local `cdd-kit gate` runs only the bounded ladder → full suite catches stragglers; (b) the full suite re-captures all contract samples → revert the churn; (c) regen both openapi files after a schema-version bump — already exist in the CLAUDE.md `cdd-kit:learnings` region (lines 112, 115, ~186) from `nav-config-to-code`; re-validated, not re-promoted. The tier-floor-scanner false-positive candidate (matched `index`/`integration`/`route`) was classified **do-not-promote**: it is self-documented by the gate message + the audited `tier-floor-override` recorded in `agent-log/audit.yml`, and would duplicate the existing line-113 `tier-floor-override` entry.

## Follow-up Work (non-blocking)
- Dead drawer-CRUD JS in the server template `src/mes_dashboard/templates/admin/pages.html` (orphaned by nav-config-to-code's endpoint removal) — out of scope here; candidate for a future cleanup.
- ui-ux low note: the status toggle flips both its visible label and `aria-pressed` simultaneously; a stable `aria-label` would be a minor a11y polish (deferred to avoid i18n churn).

## Cold Data Warning
This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
