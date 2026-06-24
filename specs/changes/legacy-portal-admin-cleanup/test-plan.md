---
change-id: legacy-portal-admin-cleanup
schema-version: 0.1.0
last-changed: 2026-06-24
risk: low
tier: 3
---

# Test Plan: legacy-portal-admin-cleanup

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit — portal_index redirect | `tests/test_app_factory.py::AppFactoryTests::test_routes_registered` (extend: assert `/` handler redirects to SPA unconditionally) | 0 |
| AC-1 | deliberate-delete | `tests/test_template_integration.py` — delete `TestPortalDynamicDrawerRendering::test_portal_uses_navigation_config_for_sidebar_links_without_iframe` | 0 |
| AC-1 | deliberate-delete | `tests/test_template_integration.py` — delete `TestPortalDynamicDrawerRendering::test_portal_hides_admin_only_drawer_for_non_admin` | 0 |
| AC-1 | deliberate-delete | `tests/test_template_integration.py` — delete `TestTemplateIntegration::test_portal_includes_base_scripts` | 0 |
| AC-1 | deliberate-delete | `tests/test_template_integration.py` — delete `TestToastCSSIntegration::test_portal_includes_toast_css` | 0 |
| AC-1 | deliberate-delete | `tests/test_portal_shell_routes.py` — remove `PORTAL_SPA_ENABLED=false` render branch from `test_wave_b_native_routes_are_reachable` | 0 |
| AC-1 | deliberate-delete | `tests/test_hold_routes.py` — delete `TestHoldDetailPageRoute::test_hold_detail_page_requires_reason_non_spa_mode` | 0 |
| AC-1 | deliberate-delete | `tests/test_yield_alert_shell_coverage.py` — delete `test_yield_alert_page_fallback_contains_vite_entry` | 0 |
| AC-2 | unit — route-name pin | `tests/test_app_factory.py::AppFactoryTests::test_routes_registered` (add assertion: rule name `portal_index` maps to `/`) | 0 |
| AC-2 | unit — flag resolution | `tests/test_app_factory.py::AppFactoryTests::test_portal_spa_flag_default_enabled` (KEEP unchanged) | 0 |
| AC-2 | unit — flag resolution | `tests/test_app_factory.py::AppFactoryTests::test_portal_spa_flag_disabled_via_env` (KEEP unchanged) | 0 |
| AC-2 | unit — flag resolution | `tests/test_app_factory.py::AppFactoryTests::test_portal_spa_flag_enabled_via_env` (KEEP unchanged) | 0 |
| AC-3 | css-governance | `frontend/src/admin-pages/style.css` — `cd frontend && npm run css:check` must pass after removing drawer-era rules | 0 |
| AC-4 | unit — frontend a11y | `frontend/src/admin-pages/__tests__/App.test.ts::test_status_toggle_exposes_aria_pressed` (new file) | 0 |
| AC-4 | unit — frontend a11y | `frontend/src/admin-pages/__tests__/PagesManagementPanel.test.ts::test_load_error_panel_has_role_alert` (new file) | 0 |
| AC-5 | unit — status payload | `tests/test_app_factory.py` — new `test_status_payload_exposes_portal_spa_enabled` | 0 |
| AC-6 | unit — absence proof | `tests/test_app_factory.py` — new `test_portal_html_template_deleted` (file-existence assertion) | 0 |
| AC-6 | unit — absence proof | `tests/test_app_factory.py` — new `test_no_portal_html_reference_in_app_source` (AST walk, per test-discipline) | 0 |
| AC-7 | test-discipline | `pytest --collect-only` must not surface any deleted test ID; no `skip`/`xfail` markers on removed paths | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit (backend) | 0 | portal_index redirect, route-name pin, status payload key, template-absence, AST proof, flag resolution |
| unit (frontend vitest) | 0 | aria-pressed reflects toggle state; role=alert on load-error panel; new files in `frontend/src/admin-pages/__tests__/` |
| deliberate-delete | 0 | 8 test removes (hard-delete, no skip/xfail); verified via collect-only in CI |
| css-governance | 0 | `npm run css:check` bounded command; no new test file |

## Out of Scope

- Contract tests: no API shape change; `portal_spa_enabled` key confirmed preserved by AC-5 unit test.
- Integration/E2E: default SPA behavior unchanged; `frontend/tests/playwright/admin-pages.spec.ts` must stay green but is not modified.
- Stress, soak, monkey, visual-review: no behavior change in default deployment path.
- `admin/pages.html` drawer-CRUD dead JS (`#drawers-tbody`, `/admin/api/drawers`): out of scope.
- `docs/migration/` manifests: untouched per design.md.

## Notes

All families target Tier 0 (unit+lint < 30 s gate). CSS governance bounded command: `cd frontend && npm run css:check`. Backend absence proofs use `pathlib.Path.exists()` + `ast` walk (see `docs/architecture/test-discipline.md`). Deliberate deletes confirmed absent from `pytest --collect-only`; no known-failure entries permitted per SDD-TDD no-waiver policy.
