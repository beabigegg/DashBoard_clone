---
change-id: rh-primary-prefilter
schema-version: 0.1.0
last-changed: 2026-06-25
risk: medium
tier: 2
---

# Test Plan: rh-primary-prefilter

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | contract | tests/contract/test_api_contract.py | 1 |
| AC-1 | unit | tests/test_reject_history_routes.py | 0 |
| AC-2 | unit | tests/test_reject_history_service.py | 0 |
| AC-2 | integration | tests/test_reject_history_routes.py | 1 |
| AC-3 | data-boundary | tests/test_reject_history_service.py | 0 |
| AC-3 | data-boundary | tests/test_reject_history_routes.py | 1 |
| AC-4 | unit | tests/test_reject_history_service.py | 0 |
| AC-4 | integration | tests/test_reject_history_routes.py | 1 |
| AC-5 | e2e | frontend/tests/playwright/reject-history-filter.spec.ts | 1 |
| AC-5 | unit | frontend/tests/validation/useRejectHistory.validation.test.js | 0 |
| AC-6 | unit | tests/test_reject_history_service.py | 0 |
| AC-6 | e2e | frontend/tests/playwright/reject-history-filter.spec.ts | 1 |
| AC-7 | integration | tests/test_reject_history_async_routes.py | 1 |
| AC-7 | e2e | frontend/tests/playwright/reject-history-filter.spec.ts | 1 |

## Test Names

### tests/test_reject_history_service.py (extend)
- `test_build_where_clause_injects_pj_types_into_base_where`
- `test_build_where_clause_injects_packages_into_base_where`
- `test_build_where_clause_injects_pj_functions_into_base_where`
- `test_build_where_clause_all_three_prefilters_combined`
- `test_build_where_clause_empty_prefilters_produce_no_restriction`
- `test_build_where_clause_absent_prefilters_produce_no_restriction`
- `test_build_where_clause_nvl_trim_form_not_raw_column_reference`
- `test_build_where_clause_prefilters_absent_from_where_clause_fragment`
- `test_na_sentinel_in_pj_types_matches_null_pj_type_rows`
- `test_na_sentinel_in_packages_matches_null_package_rows`
- `test_na_sentinel_in_pj_functions_matches_null_pj_function_rows`
- `test_pj_bop_param_absent_from_all_sql_paths`

### tests/test_reject_history_routes.py (extend)
- `test_query_route_forwards_pj_types_kwarg_to_service`
- `test_query_route_forwards_packages_kwarg_to_service`
- `test_query_route_forwards_pj_functions_kwarg_to_service`
- `test_query_route_empty_prefilters_forwarded_as_empty_list`
- `test_query_route_absent_prefilters_forwarded_as_empty_list`
- `test_pj_bop_param_silently_ignored_not_forwarded`

### tests/test_reject_history_async_routes.py (extend)
- `test_async_query_route_forwards_pj_types_kwarg`
- `test_async_query_route_forwards_packages_kwarg`
- `test_async_query_route_forwards_pj_functions_kwarg`
- `test_async_spool_cache_key_includes_all_three_prefilter_fields`
- `test_async_empty_prefilters_cache_key_equivalent_to_omitted`

### tests/contract/test_api_contract.py (extend)
- `test_reject_history_query_accepts_pj_types_param`
- `test_reject_history_query_accepts_packages_param`
- `test_reject_history_query_accepts_pj_functions_param`
- `test_openapi_root_export_has_prefilter_params`
- `test_openapi_contracts_dir_export_has_prefilter_params`

### frontend/tests/validation/useRejectHistory.validation.test.js (extend)
- `pj_types multiselect value included in primary filter payload`
- `packages multiselect value included in primary filter payload`
- `pj_functions multiselect value included in primary filter payload`
- `empty prefilter arrays sent as empty list not undefined`
- `pj_bop field absent from all request payloads`

### frontend/tests/playwright/reject-history-filter.spec.ts (extend)
- `primary section renders pj_types MultiSelect before query`
- `primary section renders packages MultiSelect before query`
- `primary section renders pj_functions MultiSelect before query`
- `pj_bop control not present anywhere in FilterPanel`
- `selecting pj_types value sends it in POST body`
- `selecting (NA) sentinel in pj_types sends sentinel string in POST body`
- `prefilter selection combined with supplementary filter in end-to-end query POST`
- `container_filter_cache options populate primary MultiSelects`

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | service `_build_where_clause` per-kwarg; route forwarding per-kwarg |
| contract | 1 | openapi param presence in both exports; request sample regeneration |
| integration | 1 | route-to-service; sync/async parity (RHPF-05); spool key coverage |
| data-boundary | 0/1 | `(NA)` sentinel; NULL-container not dropped; empty/absent params |
| e2e | 1 | FilterPanel renders three controls; PJ_BOP absent; payload content |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_reject_history_async_routes.py — _VALID_QUERY_BODY_SHORT/LONG | update | add optional prefilter fields to baseline bodies |

## Out of Scope
- PJ_BOP: verified absent only, never accepted
- Oracle index or schema migration
- Stress / soak / monkey (change is load-reducing per classification)
- Visual regression
- Modifications to `container_filter_cache` producer or production-history options endpoint

## Notes
- Use `call_args.kwargs[key]` per-kwarg assertions throughout; never `assert_called_once_with()`.
- Async-path tests: mock `is_async_available()=True` + enqueue fn; CI has no Redis.
- Module-level constants patched via `monkeypatch.setattr()`, not `setenv` (frozen at import).
- Spool/cache key tests must assert all three new fields are present (RHPF-05 parity rule).
- `(NA)` sentinel tests must confirm NULL-container rows returned, not dropped (RHPF-03).
