---
change-id: nav-config-to-code
schema-version: 0.1.0
last-changed: 2026-06-24
risk: medium
tier: 2
---

# Test Plan: nav-config-to-code

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit (JS) | `frontend/tests/legacy/portal-shell-navigation.test.js` — extend: `test_manifest_nav_tree_non_admin_matches_baseline`, `test_manifest_nav_tree_admin_matches_baseline` | 2 |
| AC-1 | unit (JS) | `frontend/tests/legacy/portal-shell-navigation.test.js` — extend: `test_drawer_order_is_1_through_6`, `test_trace_tools_page_order_is_distinct` | 2 |
| AC-1 | E2E | `frontend/tests/playwright/portal-shell-login.spec.ts` — extend: `test_non_admin_sidebar_drawers_match_baseline` | 2 |
| AC-2 | unit | `tests/test_page_registry.py` — extend `TestSetPageStatus`: `test_set_status_on_shrunk_store_persists`, `test_status_change_reflected_in_get_all_pages` | 2 |
| AC-2 | E2E | `frontend/tests/playwright/admin-pages.spec.ts` — extend: `test_status_toggle_released_to_dev_round_trip`, `test_drawer_management_panel_absent` | 2 |
| AC-3 | integration | `tests/test_admin_routes.py` — replace drawer tests with: `test_get_api_drawers_returns_404`, `test_post_api_drawers_returns_404`, `test_put_api_drawers_id_returns_404`, `test_delete_api_drawers_id_returns_404` | 2 |
| AC-3 | integration | `tests/test_admin_routes.py` — extend: `test_put_page_with_name_field_rejected`, `test_put_page_with_drawer_id_field_rejected`, `test_put_page_with_order_field_rejected` | 2 |
| AC-4 | contract | `tests/contract/test_schema_coverage.py` — update `test_endpoint_count_at_least_158` pin (minus 4 drawer ops) | 2 |
| AC-4 | contract | `tests/contract/test_manifest_completeness.py` — existing `test_manifest_keys_match_known_endpoints`, `test_all_sample_files_exist_on_disk` pass with drawer samples retired | 2 |
| AC-4 | contract | `tests/contract/test_schema_coverage.py` — existing `test_all_endpoints_have_typed_schema_ref` passes (no drawer endpoints remain) | 2 |
| AC-5 | unit (JS) | `frontend/tests/legacy/portal-shell-navigation.test.js` — extend: `test_manifest_drawer_ids_use_clean_names`, `test_manifest_excludes_test_drawer`, `test_manifest_display_names_verbatim`, `test_manifest_page_memberships_verbatim` | 2 |
| AC-5 | unit (JS) | `frontend/src/portal-shell/__tests__/navigationManifest.test.js` — new: `test_all_manifest_routes_exist_in_native_module_registry`, `test_default_status_dev_only_on_admin_dashboard` | 2 |
| AC-6 | data-boundary | `tests/test_page_registry.py` — new `TestShrunkStoreBackCompat`: `test_legacy_full_cms_file_yields_correct_statuses`, `test_missing_file_defaults_to_released`, `test_default_status_dev_hides_admin_dashboard_without_store` | 2 |
| AC-6 | data-boundary | `tests/test_page_registry.py` — extend `TestIsApiPublic`: `test_api_public_key_preserved_after_shrink` | 2 |
| AC-7 | integration | `tests/test_admin_routes.py` — see AC-3 rows; same 404/405 assertions cover AC-7 under `@admin_required` | 2 |
| AC-8 | contract | `tests/contract/test_manifest_completeness.py` — `test_all_sample_files_exist_on_disk` asserts drawer samples absent from manifest, pages sample still present | 2 |
| AC-8 | contract | `tests/contract/test_openapi_schema_resolution.py` — existing `test_openapi_operation_count_at_least_158` (update pin); `test_openapi_json_no_unresolved_refs` passes after regen | 2 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit (JS) | 2 | `buildDynamicNavigationState(manifest, statusMap)` output diff vs current-behavior.md baseline; manifest structural invariants |
| unit (Python) | 2 | `page_registry` shrunk-store get/set; back-compat read of legacy full-CMS file; `api_public` key preserved |
| integration | 2 | Removed drawer endpoints 404; non-status fields on `PUT /api/pages` rejected; all under `@admin_required` |
| contract | 2 | `test_schema_coverage`, `test_manifest_completeness`, `test_openapi_schema_resolution` pass with retired samples + slimmed pages sample |
| E2E | 2 | Admin status toggle round-trip; drawer management controls absent; non-admin sidebar structure matches baseline |
| data-boundary | 2 | Missing store / legacy full-CMS shape / `defaultStatus:'dev'` manifest annotation each fail-safe to correct status |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_admin_routes.py::test_api_drawers_success_envelope` | delete + replace with 404 assertion | `GET /api/drawers` removed (AC-3) |
| `tests/test_admin_routes.py::test_api_create_drawer_missing_name_returns_400` | delete + replace with 404 assertion | `POST /api/drawers` removed (AC-3) |
| `tests/test_admin_routes.py::test_api_create_drawer_success` | delete + replace with 404 assertion | `POST /api/drawers` removed (AC-3) |
| `tests/test_page_registry.py::TestDrawerCrud` (all 5 methods) | delete | `create/update/delete_drawer` removed from service (AC-3) |
| `tests/test_page_registry.py::TestSchemaMigration` | delete | `_migrate_navigation_schema` removed; replaced by shrunk-store back-compat tests (AC-6) |
| `tests/test_page_registry.py::TestNavigationConfig::test_navigation_config_grouped_and_sorted` | update | `get_navigation_config` signature changes to manifest+statusMap merge; assert slimmed output |
| `frontend/tests/playwright/admin-pages.spec.ts` — drawer-creation / MOCK_CREATE_DRAWER_RESP / MOCK_DRAWERS tests | delete | drawer management removed from admin UI (AC-3) |
| `tests/contract/test_schema_coverage.py::test_endpoint_count_at_least_158` | update | pin decrements by 4 for removed drawer endpoints (AC-8) |
| `tests/contract/test_openapi_schema_resolution.py::test_openapi_operation_count_at_least_158` | update | same count decrement (AC-8) |

## Out of Scope

- Visual pixel-diff / screenshot comparison (structural parity only per change-classification.md)
- Stress, soak, monkey tests (no concurrency, queue, or load surface)
- `portal_navigation_config` (`app.py`) response-shape unit test — blocked on CER-003; backend-engineer adds when approved
- `diagnostics.contract_mismatch_routes` validation test — server-side check becomes vacuous; log-only path, lower risk
- Per-user RBAC tests — binary admin vs non-admin semantics unchanged

## Notes

- AC-1 is the highest-risk test: assert the **JS object output** of `buildDynamicNavigationState`, not HTTP shape. A manifest typo yields no backend signal.
- Extend `frontend/tests/legacy/portal-shell-navigation.test.js` (already imports `buildDynamicNavigationState`/`normalizeNavigationDrawers`) rather than creating a duplicate file.
- `test_page_registry.py` `TestDrawerCrud` and `TestSchemaMigration` are retired when those service functions are removed; `TestShrunkStoreBackCompat` is their replacement.
- The data-boundary tests for AC-6 must use a real temp file fixture (matching `temp_data_file` pattern) to prove the read-path, not just mock the load function.
