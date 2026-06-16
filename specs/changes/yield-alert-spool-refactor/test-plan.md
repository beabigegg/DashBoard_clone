---
change-id: yield-alert-spool-refactor
schema-version: 0.1.0
last-changed: 2026-06-16
risk: high
tier: 1
---

# Test Plan: yield-alert-spool-refactor

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | `tests/test_yield_alert_routes.py::test_query_rejects_invalid_process_type` | 0 |
| AC-1 | integration | `tests/test_yield_alert_routes.py::test_query_forwards_process_type_kwarg` | 1 |
| AC-1 | e2e | `tests/e2e/test_yield_alert_e2e.py::TestYieldAlertBrowserE2E::test_process_type_switch_ga_to_gc` | 1 |
| AC-2 | unit | `tests/test_yield_alert_service.py::test_query_yield_trend_no_longer_calls_oracle` | 0 |
| AC-2 | integration | `tests/test_yield_alert_routes.py::test_trend_serves_from_spool_not_oracle` | 1 |
| AC-2 | resilience | `tests/e2e/test_yield_alert_e2e.py::TestYieldAlertView::test_spool_missing_returns_410_no_oracle_fallback` | 1 |
| AC-3 | data-boundary | `tests/test_yield_alert_dataset_cache.py::test_ga_pct_totals_match_baseline` | 1 |
| AC-4 | unit | `tests/test_yield_alert_dataset_cache.py::test_source_code_not_null_rows_have_tx_zero` | 0 |
| AC-4 | contract | `frontend/tests/validation/useYieldAlert.validation.test.js` | 1 |
| AC-4 | e2e | `tests/e2e/test_yield_alert_e2e.py::TestYieldAlertAlerts::test_alert_list_shows_source_code_column` | 1 |
| AC-5 | unit | `tests/test_yield_alert_dataset_cache.py::test_reject_linked_column_present_in_spool_row` | 0 |
| AC-5 | unit | `tests/test_yield_alert_service.py::test_reject_linkage_normalization_upper_trim_matches_old_path` | 0 |
| AC-6 | unit | `tests/test_yield_alert_dataset_cache.py::test_schema_version_bumped` | 0 |
| AC-6 | stress | `tests/stress/test_yield_alert_stress.py::TestYieldAlertSpoolBuildStress::test_spool_build_latency_under_1m_rows` | 3 |
| AC-7 | data-boundary | `tests/test_yield_alert_dataset_cache.py::test_ga_pct_package_na_count_is_zero` | 1 |
| AC-7 | data-boundary | `tests/test_yield_alert_dataset_cache.py::test_gc_pct_package_na_retained` | 1 |
| AC-8 | unit | `frontend/tests/yield-alert/App.cross-filter.test.js` | 0 |
| AC-8 | resilience | `frontend/tests/abort/yield-alert-abort.test.js` | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | spool row-shape, SOURCE_CODE NOT NULL→TX=0 invariant, process_type validation, live-Oracle-removal, reject-linkage normalization, _SCHEMA_VERSION value pin |
| contract | 1 | API response shape (type param, source_code field) vs response-samples.json; frontend schema-guard via useYieldAlert.validation.test.js |
| integration | 1 | route→service→spool mock-integration; process_type kwarg per-call assertions (call_args.kwargs); both snapshot + spool-miss paths |
| e2e | 1 | Playwright: type switch GA%↔GC%, all 4 views from spool, LOT column visible in alert table, 410 re-query flow |
| data-boundary | 1 | GA% PACKAGE=NA count=0; GC% PACKAGE=NA retained; null/malformed SOURCE_CODE rows; GA% totals baseline |
| resilience | 1 | spool-warmup failure → 410 with no Oracle fallback; in-flight abort unchanged |
| stress | 3 | 1M-row spool build time + DuckDB browser-query p95 under 2.4x volume (nightly) |
| soak | 4 | rq_yield_alert_worker warmup with larger spool over sustained run (weekly lane) |

## Test File Index

| file path | existing/new | tests to add (names only) |
|---|---|---|
| `tests/test_yield_alert_routes.py` | existing | `test_query_rejects_invalid_process_type`, `test_query_forwards_process_type_kwarg`, `test_trend_serves_from_spool_not_oracle`, `test_summary_serves_from_spool_not_oracle` |
| `tests/test_yield_alert_dataset_cache.py` | existing | `test_primary_query_process_type_ga_filters_entity_name`, `test_primary_query_process_type_gc_filters_entity_name`, `test_source_code_not_null_rows_have_tx_zero`, `test_reject_linked_column_present_in_spool_row`, `test_ga_pct_package_na_count_is_zero`, `test_gc_pct_package_na_retained`, `test_ga_pct_totals_match_baseline`, `test_schema_version_bumped` |
| `tests/test_yield_alert_service.py` | existing | `test_query_yield_trend_no_longer_calls_oracle`, `test_query_yield_summary_no_longer_calls_oracle`, `test_reject_linkage_normalization_upper_trim_matches_old_path` |
| `tests/e2e/test_yield_alert_e2e.py` | existing | `test_process_type_switch_ga_to_gc` (in `TestYieldAlertBrowserE2E`), `test_alert_list_shows_source_code_column` (in `TestYieldAlertAlerts`), `test_spool_missing_returns_410_no_oracle_fallback` (in `TestYieldAlertView`) |
| `tests/stress/test_yield_alert_stress.py` | existing | new class `TestYieldAlertSpoolBuildStress` with `test_spool_build_latency_under_1m_rows`, `test_duckdb_view_query_p95_under_2x_volume` |
| `frontend/tests/validation/useYieldAlert.validation.test.js` | existing | add `source_code` to `ALERT_ITEM_SHAPE`; add `test_alert_item_includes_source_code_field`, `test_process_type_param_accepted_in_query_schema` |
| `frontend/tests/yield-alert/App.cross-filter.test.js` | existing | `test_process_type_selector_propagates_to_all_views`, `test_other_filter_orchestrator_consumers_unaffected` |
| `frontend/tests/abort/yield-alert-abort.test.js` | existing | regression-only; extend only if abort path changed by this refactor |
| `frontend/tests/legacy/yield-alert-center-utils.test.js` | existing | regression-only |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_yield_alert_service.py::test_compute_reject_linkage_batches_workorders_for_oracle_in_limit` | delete | `_compute_reject_linkage` separate Oracle round-trip removed (AC-5/D3) |
| `tests/test_yield_alert_service.py::test_query_yield_trend_uses_movetxn_for_transaction_and_filtered_detail_for_scrap` | update | live Oracle trend path retired; test must assert spool-query path, not Oracle (AC-2) |

## Out of Scope
- WIP, Hold, reject-history, resource-history pages (AC-8 guards via existing suites)
- CSS contract changes (confirm-only; no new rules)
- Env-var contract (no new env var)
- LDAP/auth path (not touched)
- Monkey/fuzz: existing route fuzz coverage sufficient per change-classification

## Notes
- `test_source_code_not_null_rows_have_tx_zero` pins the D4 invariant; it must fail before implementation (column absent from current spool schema).
- `test_schema_version_bumped`: pin the new integer value (5), not just presence.
- Use `call_args.kwargs[key]` per-kwarg assertions for `process_type` forwarding (test-discipline rule).
- Stress/soak tests are Tier 3/4; they do not block PR merge.
- After contract-reviewer edits api-contract.md, regen `contracts/openapi.json` and `tests/contract/response-samples.json` before running contract phase.
