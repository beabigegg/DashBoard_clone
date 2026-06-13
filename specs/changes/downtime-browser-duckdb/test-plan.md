---
change-id: downtime-browser-duckdb
schema-version: 0.1.0
last-changed: 2026-06-12
risk: high
tier: 0
---

# Test Plan: downtime-browser-duckdb

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | test name / description | tier |
|---|---|---|---|---|
| AC-1 | unit | tests/test_downtime_analysis_routes.py | `TestQueryRoute::test_response_shape_has_all_four_keys` | Tier 0 |
| AC-1 | unit | tests/test_downtime_analysis_routes.py | `TestQueryRoute::test_base_spool_url_non_null` | Tier 0 |
| AC-1 | unit | tests/test_downtime_analysis_routes.py | `TestQueryRoute::test_jobs_spool_url_non_null` | Tier 0 |
| AC-1 | unit | tests/test_downtime_analysis_routes.py | `TestQueryRoute::test_query_id_non_null` | Tier 0 |
| AC-1 | unit | tests/test_downtime_analysis_routes.py | `TestQueryRoute::test_taxonomy_non_null` | Tier 0 |
| AC-1 | unit | tests/test_downtime_analysis_routes.py | `TestQueryRoute::test_legacy_keys_absent_when_flag_on` (summary/daily_trend/big_category/top_reasons absent) | Tier 0 |
| AC-1 | contract | tests/test_downtime_analysis_routes.py | `TestQueryRouteContract::test_response_shape_conforms_to_api_contract_v1_15` | Tier 0 |
| AC-2 | unit | tests/test_downtime_analysis_service.py | `TestRawSpoolWriter::test_base_events_parquet_written_without_merge` | Tier 0 |
| AC-2 | unit | tests/test_downtime_analysis_service.py | `TestRawSpoolWriter::test_job_bridge_parquet_written_raw` | Tier 0 |
| AC-2 | unit | tests/test_downtime_analysis_service.py | `TestRawSpoolWriter::test_merge_cross_shift_not_called_on_request_path` | Tier 0 |
| AC-2 | unit | tests/test_downtime_analysis_service.py | `TestRawSpoolWriter::test_schema_version_in_cache_key` (D4) | Tier 0 |
| AC-2 | integration | tests/test_downtime_analysis_service.py | `TestPrewarmFeedRawWriter::test_prewarm_path_writes_same_raw_parquet` | Tier 0 |
| AC-3 | unit | frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts | `test_cross_shift_merge_parity_vs_reference_fixture` | Tier 0 |
| AC-3 | unit | frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts | `test_job_overlap_bridge_parity_vs_reference_fixture` | Tier 0 |
| AC-3 | unit | frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts | `test_kpi_summary_parity_vs_reference_fixture` | Tier 0 |
| AC-3 | unit | frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts | `test_big_category_aggregation_parity_vs_reference_fixture` | Tier 0 |
| AC-3 | unit | frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts | `test_daily_trend_parity_vs_reference_fixture` | Tier 0 |
| AC-3 | unit | frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts | `test_equipment_detail_table_parity_vs_reference_fixture` | Tier 0 |
| AC-3 | unit | frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts | `test_event_detail_table_parity_vs_reference_fixture` | Tier 0 |
| AC-4 | unit | tests/test_downtime_analysis_service.py | `TestTaxonomyBuilder::test_taxonomy_json_shape_has_map_prefixes_egt_fallback` | Tier 0 |
| AC-4 | unit | tests/test_downtime_analysis_service.py | `TestTaxonomyBuilder::test_taxonomy_map_covers_all_nine_buckets` | Tier 0 |
| AC-4 | unit | frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts | `test_taxonomy_driven_big_category_identical_to_prior_server_map` | Tier 0 |
| AC-5 | e2e | frontend/tests/playwright/downtime-analysis.spec.ts | `test_filter_change_issues_zero_api_round_trips` | Tier 0 |
| AC-6 | unit | tests/test_downtime_analysis_routes.py | `TestQueryRoute::test_range_over_90_days_returns_200_not_400` | Tier 0 |
| AC-6 | unit | tests/test_downtime_analysis_service.py | `TestMaxOracleDaysRemoved::test_max_oracle_days_constant_absent` | Tier 0 |
| AC-6 | e2e | frontend/tests/playwright/downtime-analysis.spec.ts | `test_180_day_range_accepted_end_to_end` | Tier 0 |
| AC-7 | resilience | tests/test_downtime_analysis_service.py | `TestTwoParquetAtomicity::test_base_hit_jobs_miss_raises_loudly` | Tier 0 |
| AC-7 | e2e | frontend/tests/playwright/downtime-analysis.spec.ts | `test_wasm_init_failure_shows_error_banner_not_empty_table` | Tier 0 |
| AC-7 | e2e | frontend/tests/playwright/downtime-analysis.spec.ts | `test_parquet_fetch_404_shows_error_banner` | Tier 0 |
| AC-7 | stress | tests/stress/test_downtime_analysis_stress.py | `test_concurrent_wide_range_queries_no_oom_kill` | Tier 4 |
| AC-8 | unit | frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts | `test_csv_export_blob_equals_rendered_data` | Tier 0 |
| AC-8 | e2e | frontend/tests/playwright/downtime-analysis.spec.ts | `test_csv_export_download_triggers_browser_blob` | Tier 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | Tier 0 | Route shape, service raw-write, taxonomy, 90d removal, flag toggle, parity composable |
| contract | Tier 0 | /query response shape vs api-contract 1.15.0; parquet column/type schema vs data-shape-contract §3.13 |
| integration | Tier 0 | Oracle-fallback path + prewarm-cache path both write raw parquets; all filter kwargs forwarded per-kwarg |
| e2e (Playwright) | Tier 0 | Full browser flow; zero-round-trip filter; error banners; >90d acceptance; CSV blob |
| data-boundary | Tier 0 | Empty parquets, null OLDREASONNAME, CHAR trailing-space, cross-midnight event, no-overlap job |
| resilience | Tier 0 | Two-parquet atomicity; parquet fetch timeout; DuckDB reduction error |
| stress | Tier 4 | Concurrent wide-range queries under 6 GB/no-swap; spool TTL reclaim stability |
| soak | Tier 4 | Repeated 90d+ queries; memory stable after 50 runs |

## Existing Tests to Extend (not duplicate)

- `tests/test_downtime_analysis_routes.py` — extend `TestSummaryRoute` → rename/repurpose to `TestQueryRoute`; add new response-shape assertions alongside existing per-kwarg forwarding tests. The existing `test_start_date_forwarded` … `test_package_groups_forwarded` pattern must be retained verbatim (per-kwarg assertion discipline) and extended with `feature_flag=True` fixture.
- `tests/test_downtime_analysis_service.py` — extend `TestCrossShiftMerge` and `TestJobidBridge` with a `_flag_on` variant that asserts the reductions are NOT called on the request path; retain the existing reduction-correctness tests as the Python reference for parity.
- `tests/e2e/test_downtime_analysis_e2e.py` — extend `TestSummaryEndpointIntegration` to cover the new `/query` shape; existing tests for the deprecated endpoints are preserved as regression coverage until api 1.17.0 removal.
- `frontend/tests/playwright/downtime-analysis.spec.js` → migrate to `.spec.ts`; extend with browser-DuckDB flow, zero-round-trip, error-banner, and CSV tests.

## Parity Fixture Note

The 184k-row reference dataset lives at `tests/fixtures/downtime_184k_reference/` (base_events.parquet + job_bridge.parquet). Both the Python pandas functions (`_merge_cross_shift_events`, `_bridge_jobid`, `_map_big_category`) and the browser DuckDB SQL run against the identical files. A parity test passes only if the row count, column values, and aggregated totals are byte/row-equivalent between paths. The fixture must include at least one cross-midnight event and one ambiguous job-bridge tie-break case (≥80% runner-up) to distinguish a correct from a silently-corrupt SQL implementation.

## Out of Scope

- `/view`, `/equipment-detail`, `/event-detail` route behavior changes — these are deprecated-in-place (D1); existing route tests remain as-is until api 1.17.0 removal.
- DuckDB prewarm cache internals (`downtime_analysis_duckdb_cache.py`) — D6 confirms no code change; existing prewarm tests are regression-only.
- CSS / portal-shell theming — no change; css:check gate unchanged.
- Resource-history DuckDB composable — read as pattern reference only; no new tests added to that module.
- Server-side CSV streamers (`export_*_csv`) — kept as deprecated fallback behind flag-off; no new tests required.

## Notes

- Patch `load_downtime_events` at `mes_dashboard.services.downtime_analysis_cache.load_downtime_events` — never at the service module level (CLAUDE.md).
- Feature-flag tests must use `monkeypatch.setattr("mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED", True/False)` — not `os.environ`.
- Integration tests that touch Oracle fallback must be in an unmarked file (not `tests/integration/test_oracle_error_path.py`) to avoid `pytestmark = pytest.mark.integration_real` silent skip.
- Parity tests must use a fixture where Python and SQL produce different results if the SQL is wrong — a uniform fixture cannot distinguish a correct from an incorrect merge.
- Two-parquet atomicity test: simulate `jobs` key expired (mock `query_spool_store.load` returning None for job_bridge key only) and assert the service raises, not silently returns empty join.
