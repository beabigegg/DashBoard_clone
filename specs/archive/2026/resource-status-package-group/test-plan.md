---
change-id: resource-status-package-group
schema-version: 0.1.0
last-changed: 2026-05-21
risk: medium
tier: 2
---

# Test Plan: resource-status-package-group

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | tests/test_resource_service.py | 0 |
| AC-1 | integration | tests/test_resource_service.py | 1 |
| AC-2 | unit | frontend/tests/legacy/resource-status.test.js | 0 |
| AC-3 | unit | frontend/tests/legacy/resource-status.test.js | 0 |
| AC-4 | unit | tests/test_resource_routes.py | 0 |
| AC-4 | unit | tests/test_resource_service.py | 0 |
| AC-5 | unit | tests/test_resource_cache.py | 0 |
| AC-5 | data-boundary | tests/test_resource_cache.py | 0 |
| AC-6 | unit | tests/test_resource_cache.py | 0 |
| AC-7 | contract | tests/test_resource_routes.py | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | backend cache/service/route + frontend component tests; must run in < 30 s |
| contract | 1 | API response shape + data-shape nullable field; run in pre-merge CI |
| integration | 1 | filter kwarg applied on both warm-cache path and Oracle-fallback path |
| data-boundary | 0 | NULL PACKAGEGROUPID (91% case), CHAR trailing-space key, empty `package_groups` list |

## Backend Unit Tests — tests/test_resource_cache.py

- `TestPackageGroupLookup::test_builds_lookup_dict_from_oracle_rows`
- `TestPackageGroupLookup::test_char_key_trailing_space_stripped_on_build`
- `TestPackageGroupLookup::test_lookup_ttl_is_7_days_independent_of_resource_cache`
- `TestPackageGroupLookup::test_null_packagegroupid_resolves_to_none`
- `TestPackageGroupLookup::test_unknown_packagegroupid_resolves_to_none`
- `TestPackageGroupLookup::test_char_key_trailing_space_stripped_on_resolve`

## Backend Unit Tests — tests/test_resource_service.py

- `TestGetMergedResourceStatus::test_packagegroupname_added_when_packagegroupid_present`
- `TestGetMergedResourceStatus::test_packagegroupname_is_none_when_packagegroupid_null`
- `TestGetMergedResourceStatus::test_package_groups_filter_warm_cache_path`
- `TestGetMergedResourceStatus::test_package_groups_filter_oracle_fallback_path`
- `TestGetMergedResourceStatus::test_package_groups_empty_list_returns_all_resources`
- `TestQueryResourceFilterOptions::test_returns_package_groups_list`
- `TestQueryResourceFilterOptions::test_package_groups_excludes_null_entries`

## Backend Unit Tests — tests/test_resource_routes.py

- `test_resource_status_forwards_package_groups_kwarg`
- `test_resource_filter_options_returns_package_groups_field`
- `test_resource_status_package_groups_non_default_value_forwarded`

## Frontend Unit Tests — frontend/tests/legacy/resource-status.test.js

- `EquipmentCard shows PACKAGEGROUPNAME row when value is present`
- `EquipmentCard hides PACKAGEGROUPNAME row when value is null`
- `EquipmentCard hides PACKAGEGROUPNAME row when value is empty string`
- `FilterBar renders Package Group MultiSelect`
- `FilterBar emits package_groups filter on MultiSelect change`
- `MatrixSection renders Package dimension column`
- `MatrixSection Package dimension does not alter OU% or AVAIL% values`

## Out of Scope

- E2E (Playwright browser tests)
- Resilience / chaos / monkey tests
- Stress / soak tests
- Cross-filter narrowing between Package Group and other dimensions (non-goal; pin with does_not_narrow test only if resource-status already cross-filters; otherwise omit)
- Visual pixel-diff regression (handled by ui-ux-reviewer agent log)
- Other feature pages (resource-history, dashboard) — non-goal per change-request

## Notes

Route-forwarding tests must supply a non-default value (e.g., `?package_groups=PKG-A`) and assert `mock.call_args.kwargs['package_groups'] == ['PKG-A']` — do NOT use `assert_called_once_with(...)` per CLAUDE.md discipline.
Both warm-cache and Oracle-fallback paths in `get_merged_resource_status()` must be tested for the `package_groups` kwarg; mock at the cache-read boundary for the warm path and `read_sql_df` for the Oracle path.
CHAR key normalization must be tested with a key containing a trailing space (e.g., `'P01 '` → resolves same as `'P01'`).
The 7-day TTL test must assert the lookup dict refresh timer is stored independently from the 24 h resource-cache timestamp.
