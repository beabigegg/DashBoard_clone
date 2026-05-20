---
change-id: material-part-consumption
schema-version: 0.1.0
last-changed: 2026-05-20
risk: high
tier: 1
---

# Test Plan: material-part-consumption

## Acceptance Criteria — Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 aggregation | unit | `tests/test_material_consumption_service.py` | 0 |
| AC-1 route kwarg forwarding | unit | `tests/test_material_consumption_routes.py` | 0 |
| AC-2 trend chart series + granularity regroup | unit + e2e | `frontend/src/material-consumption/__tests__/TrendChart.test.ts` | 0/1 |
| AC-3 granularity switch no Oracle re-query (MC-03) | unit + resilience | `tests/test_material_consumption_service.py` | 0/1 |
| AC-4 PJ_TYPE JOIN + pj_types kwarg forwarding | unit | `tests/test_material_consumption_service.py`, `tests/test_material_consumption_routes.py` | 0 |
| AC-5 sync vs async detail threshold (MC-04) | unit + resilience | `tests/test_material_consumption_service.py`, `tests/test_material_consumption_routes.py` | 0/1 |
| AC-6 CSV chunked stream | unit + e2e | `tests/test_material_consumption_service.py`, `frontend/tests/playwright/material-consumption.spec.ts` | 0/1 |
| AC-7 RQ queue in rq_monitor | unit + integration | `tests/test_material_consumption_routes.py` | 0/1 |
| AC-8 drawer-2 registration; CSS scope; gunicorn startup | contract + e2e | `tests/test_modernization_policy_hardening.py` (extend) | 0/1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Oracle path AND spool/regroup path per kwarg; mock at service boundary |
| contract | 0/1 | API payload shape, CSS scope via `npm run css:check`, data-shape-contract §3.9 parquet schema |
| integration | 1 | Route → service wiring; rq_monitor queue name; startup asset-readiness manifest |
| e2e | 1 | Critical journey: submit → chart → granularity switch → detail → CSV download |
| data-boundary | 1 | 20-part cap, 0-row result, wildcard edge cases, SQL meta-char rejection (MC-02) |
| resilience | 1 | Spool miss → 410; Redis unavailable → fallback; worker absent → job queues |
| fuzz/monkey | 1 | SQL meta-char and wildcard token inputs; extend `tests/routes/test_fuzz_routes.py` |
| stress | 3 | 17.8M-row multi-part wildcard summary ≤ 5 s; nightly, not pre-merge |
| soak | 4 | Cache hit ≤ 2 s (SYS-02) on granularity switches over 8 h; weekly |

## Test Files and Named Tests

### `tests/test_material_consumption_routes.py` (unit/integration, Tier 0-1)
- `TestFilterOptions::test_returns_material_parts_and_pj_type_lists`
- `TestQuerySubmit::test_forwards_material_parts_kwarg_non_default`
- `TestQuerySubmit::test_forwards_date_range_kwargs_non_default`
- `TestQuerySubmit::test_over_20_parts_returns_400`
- `TestQuerySubmit::test_sql_meta_char_in_part_returns_400`
- `TestQuerySubmit::test_wildcard_star_accepted`
- `TestViewEndpoint::test_forwards_granularity_kwarg_non_default`
- `TestViewEndpoint::test_forwards_query_id_kwarg`
- `TestDetailSubmit::test_sync_path_when_rows_under_threshold`
- `TestDetailSubmit::test_async_202_when_rows_over_threshold`
- `TestDetailSubmit::test_forwards_pj_types_kwarg_non_default`
- `TestDetailJob::test_poll_returns_job_status`
- `TestExport::test_export_returns_streaming_response`
- `TestRqMonitor::test_material_consumption_queue_in_rq_monitor_queue_names`

### `tests/test_material_consumption_service.py` (unit, Tier 0)
- `TestSummaryOraclePath::test_aggregates_consumed_required_by_txn_date`
- `TestSummaryOraclePath::test_pj_type_join_filters_correctly`
- `TestSummaryOraclePath::test_material_parts_kwarg_forwarded_to_sql`
- `TestSummarySpoolPath::test_granularity_week_regroups_without_oracle`
- `TestSummarySpoolPath::test_granularity_month_regroups_without_oracle`
- `TestSummarySpoolPath::test_granularity_quarter_regroups_without_oracle`
- `TestSummarySpoolPath::test_spool_miss_raises_cache_expired`
- `TestDetailOraclePath::test_sync_rows_under_limit_returns_inline`
- `TestDetailOraclePath::test_rows_over_limit_enqueues_rq_job`
- `TestDetailSpoolPath::test_pagination_returns_correct_page`
- `TestDetailSpoolPath::test_pj_types_filter_applied_on_both_paths`
- `TestCsvExport::test_streams_chunks_without_full_memory_load`
- `TestInputValidation::test_parts_cap_20_enforced`
- `TestInputValidation::test_wildcard_translated_to_like_escaped`
- `TestInputValidation::test_exact_token_uses_in_list`
- `TestInputValidation::test_meta_char_rejected_before_oracle`
- `TestIdempotentSpoolWrite::test_spool_exists_skips_oracle_query`

### `frontend/src/material-consumption/__tests__/` (Vitest unit, Tier 0)
- `TrendChart.test.ts::renders_one_series_per_material_part`
- `TrendChart.test.ts::caps_at_20_series`
- `TrendChart.test.ts::emits_granularity_change_without_query_reload`
- `useConsumptionQuery.test.ts::polls_job_status_until_done`
- `useConsumptionQuery.test.ts::resets_on_new_query_submit`
- `FilterPanel.test.ts::clears_selection_on_reset`

### `frontend/tests/playwright/material-consumption.spec.ts` (E2E, Tier 1)
- `test_critical_journey_query_submit_to_trend_chart`
- `test_granularity_switch_does_not_trigger_new_oracle_request`
- `test_detail_async_polling_resolves_to_table`
- `test_csv_export_download_starts`
- `test_css_no_bleed_into_adjacent_page`
- `test_drawer2_link_navigates_to_page`

### `frontend/tests/playwright/material-consumption-resilience.spec.ts` (resilience, Tier 1)
- `test_spool_miss_410_triggers_client_requery`
- `test_filter_options_error_shows_inline_error`
- `test_detail_worker_absent_shows_pending_state`

### `frontend/tests/playwright/material-consumption-data-boundary.spec.ts` (data-boundary, Tier 1)
- `test_21_parts_rejected_with_validation_error`
- `test_0_row_result_shows_empty_state`
- `test_wildcard_bare_star_rejected`
- `test_sql_injection_attempt_returns_400`

### `tests/stress/test_material_consumption_stress.py` (stress, Tier 3 — nightly)
- `test_summary_aggregate_large_table_under_5s`
- `test_concurrent_granularity_switches_cache_only`

## Out of Scope
- DuckDB prewarm path (MC-05 — intentionally absent; no test needed) [already listed below]
- DuckDB prewarm path (MC-05 — intentionally absent; no test needed)
- LDAP/AD auth flows (covered by existing `test_auth_service.py`; not changed)
- Soak tests pre-merge (weekly Tier 4 gate)
- Systemd watchdog unit E2E (infrastructure-level; verified in nightly integration environment)

## Notes
- Both Oracle fallback AND spool/regroup paths must be tested per kwarg; fixture DataFrames must include `pj_type`, `material_part`, and date columns so filter functions cannot silently no-op (CLAUDE.md Test Coverage Discipline).
- Use `mock.assert_called_once()` + `call_args.kwargs[key] == value` per kwarg; do NOT use `assert_called_once_with(...)`.
- Extend `tests/test_modernization_policy_hardening.py` for AC-8 asset-readiness + page_status.json assertions rather than duplicating the fixture pattern.
- Stress tests run nightly (Tier 3); not in PR required gates.
- `TestSummarySpoolPath` and `TestDetailSpoolPath` are the anti-regression surface for silent filter drops on warm-cache production traffic (the dominant path).
