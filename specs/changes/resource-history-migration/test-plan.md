---
change-id: resource-history-migration
schema-version: 0.1.0
last-changed: 2026-06-19
risk: high
tier: 1
---

# Test Plan: resource-history-migration

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit regression | tests/test_resource_history_service.py | 0 |
| AC-1 | integration | tests/integration/test_resource_history_rq_async.py | 1 |
| AC-2 | unit | tests/test_resource_history_unified_job.py | 0 |
| AC-3 | data-boundary | tests/test_resource_history_unified_job.py | 0 |
| AC-3 | integration parity | tests/integration/test_resource_history_rq_async.py | 1 |
| AC-4 | unit parity | tests/test_resource_history_unified_job.py | 0 |
| AC-5 | unit | tests/test_resource_history_job_service.py | 0 |
| AC-6 | contract | tests/test_resource_history_unified_job.py | 0 |
| AC-7 | resilience | tests/test_resource_history_service.py | 0 |
| AC-8 | contract | tests/test_query_cost_policy.py | 0 |
| AC-8 | contract | tests/test_resource_history_service.py | 0 |
| AC-9 | contract | tests/test_async_query_job_service.py | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Job class construction, chunk strategy, requires_cross_chunk_reduction, iterrows→SQL parity |
| contract | 0 | _APPROVED_CALLERS, ASYNC-09 presence, env default pin (`off`), spool schema UNCHANGED |
| data-boundary | 0 | OEE ±30d reject seam: NG at chunk boundary captured; ratio-of-SUMs parity ≤1e-6 |
| resilience | 0 | flag=on + no worker → 503; sync-fallback code absent via ast.parse probe |
| integration | 1 | parity vs legacy single-pass on synthetic Oracle fixture; flag dispatch end-to-end |

## Test File Paths and Test Names

**`tests/test_resource_history_unified_job.py`** (new — Tier 0)
- `TestResourceHistoryBaseJob::test_requires_cross_chunk_reduction_is_false`
- `TestResourceHistoryBaseJob::test_chunk_strategy_is_time`
- `TestResourceHistoryBaseJob::test_build_chunk_sql_binds_date_range`
- `TestResourceHistoryOeeJob::test_requires_cross_chunk_reduction_is_true`
- `TestResourceHistoryOeeJob::test_build_chunk_sql_extends_reject_window_30d_before_chunk_start`
- `TestResourceHistoryOeeJob::test_build_chunk_sql_extends_reject_window_30d_after_chunk_end`
- `TestOeeChunkSeamParity::test_ng_event_at_chunk_boundary_captured_in_output`
- `TestOeeChunkSeamParity::test_ng_event_within_30d_window_captured`
- `TestOeeChunkSeamParity::test_ng_event_beyond_30d_window_excluded`
- `TestOeeChunkSeamParity::test_oee_ratio_of_sums_matches_single_pass_within_1e6`
- `TestIterrowsReplacement::test_duckdb_join_output_matches_iterrows_output`
- `TestIterrowsReplacement::test_duckdb_join_handles_zero_denominator`
- `TestSpoolSchemaUnchanged::test_base_parquet_columns_match_legacy_schema`
- `TestSpoolSchemaUnchanged::test_oee_parquet_columns_match_legacy_schema`

**`tests/test_resource_history_job_service.py`** (new — Tier 0)
- `TestUnifiedJobDispatch::test_flag_on_enqueues_base_job`
- `TestUnifiedJobDispatch::test_flag_on_enqueues_oee_job`
- `TestUnifiedJobDispatch::test_flag_on_enqueues_both_jobs_in_same_call`
- `TestUnifiedJobDispatch::test_flag_off_uses_legacy_path_not_unified`
- `TestUnifiedJobDispatch::test_flag_patched_via_setattr_not_setenv`

**`tests/test_resource_history_service.py`** (extend — Tier 0)
- `TestExportCsv::test_flag_off_behavior_unchanged` (add to existing class)
- `TestDegradedPath::test_flag_on_no_worker_returns_503`
- `TestSyncFallbackAbsent::test_sync_fallback_not_present_in_unified_path` (ast.parse probe)
- `TestEnvDefaultPin::test_use_unified_job_default_is_off`

**`tests/test_query_cost_policy.py`** (extend — Tier 0)
- `TestNoPandasAndNoCallers::test_no_caller_outside_tests` — extend `_APPROVED_CALLERS` to include `resource_history_base_worker` and `resource_history_oee_worker`

**`tests/test_async_query_job_service.py`** (extend — Tier 0)
- `TestResourceHistoryBaseJobRegistry::test_base_job_registered_always_async_false`
- `TestResourceHistoryBaseJobRegistry::test_base_job_queue_name`
- `TestResourceHistoryOeeJobRegistry::test_oee_job_registered_always_async_false`
- `TestResourceHistoryOeeJobRegistry::test_oee_job_queue_name`
- Both classes use `importlib.reload()` after clearing the registry dict (AC-9 pattern)

**`tests/integration/test_resource_history_rq_async.py`** (extend — Tier 1, `integration_real`)
- `TestUnifiedJobParity::test_base_job_parity_vs_legacy_spool`
- `TestUnifiedJobParity::test_oee_job_parity_vs_legacy_spool`

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_resource_history_service.py::TestExportCsv::test_successful_export | verify | must still pass under flag=off (AC-1 regression guard) |

## Data-Boundary Strategy (AC-3 highest risk)

Three synthetic fixtures exercise the ±30d reject sub-window seam:
1. NG row's reject date = chunk-N last day; producing trackout = chunk-N+1 first day — assert NG captured.
2. NG event 29d before producing trackout — assert captured (within window).
3. NG event 31d before producing trackout — assert excluded (outside window).

Parity fixture: same base+OEE rows run through legacy `iterrows` path → result_A, then through DuckDB `post_aggregate` SQL → result_B; assert `abs(result_A[col] - result_B[col]) ≤ 1e-6` per numeric column per EQUIPMENTID.

## Out of Scope

- Frontend / Playwright E2E (flag off by default; no frontend surface)
- Stress / soak (deferred via tier-floor-override in tasks.yml)
- API contract edits (confirm-only; no response shape change)
- CSS / visual review (no UI change)

## Notes

- Flag-toggle tests must use `monkeypatch.setattr` on the module-level constant, not `setenv` (frozen at import; test-discipline §Module-Level Constants).
- AC-9 registry tests must use `importlib.reload()` to re-run `register_job_type()` side-effects after clearing the registry dict.
- New mock-based dispatch tests go to `test_resource_history_job_service.py` (unmarked); only real-Oracle parity tests belong in the `integration_real`-marked integration file.
- `ast.parse()` probe is the only reliable absence proof for AC-7 sync-fallback removal.
