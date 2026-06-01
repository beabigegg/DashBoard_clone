---
change-id: batch-rowcount-unification
schema-version: 0.1.0
last-changed: 2026-06-01
risk: high
tier: 1
---

# Test Plan: batch-rowcount-unification

## Acceptance Criteria — Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1: decompose_by_row_count correctness (4 edge cases) | unit | `tests/test_batch_query_engine.py` | Tier 0 |
| AC-1: no gap/overlap invariant (property-based) | unit | `tests/test_batch_query_engine.py` | Tier 0 |
| AC-2: flag=false → row-identical spool (all 7 services) | integration | `tests/integration/test_rowcount_flag_parity.py` | Tier 1 |
| AC-3: flag=true → complete row set, no drop/dupe at seams | integration | `tests/integration/test_rowcount_flag_parity.py` | Tier 1 |
| AC-3: chunk boundary off-by-one / ORDER BY tie-stability | data-boundary | `tests/stress/test_chunk_boundary.py` (extend) | Tier 1 |
| AC-4: downtime migration — BatchQueryEngine path, no direct Oracle→spool | integration | `tests/test_downtime_analysis_service.py` (extend) | Tier 1 |
| AC-4: downtime spool namespace/schema unchanged | contract | `tests/test_downtime_analysis_service.py` (extend) | Tier 1 |
| AC-5: spool parquet column schema identical between paths (all 7) | contract | `tests/integration/test_rowcount_flag_parity.py` | Tier 1 |
| AC-6: ENGINE_PARALLEL env-configurable; ceiling ≤ DB_SLOW_POOL_SIZE | unit | `tests/test_batch_query_engine.py` | Tier 0 |
| AC-6: env-contract documented (4 new vars) | contract | `tests/test_env_contract.py` (extend) | Tier 1 |
| AC-7: spool TTL/cleanup/memory-guard unchanged | integration | `tests/integration/test_rowcount_flag_parity.py` | Tier 1 |
| AC-8: excluded services not modified | unit | `tests/test_batch_query_engine.py` | Tier 0 |
| count/paged consistency under concurrent insert | resilience | `tests/integration/test_race_conditions.py` (extend) | Tier 3 |
| partial-chunk Oracle failure → no partial spool written | resilience | `tests/integration/test_oracle_error_path.py` (extend) | Tier 1 |
| parallel-execution peak memory profile (flag=true) | stress | `tests/stress/test_chunk_boundary.py` (extend) | Tier 4 |
| sustained memory uniformity vs date-range (soak) | soak | `tests/integration/test_soak_workload.py` (extend) | Tier 4 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | Tier 0 | decompose_by_row_count 4 edge cases + property; ENGINE_PARALLEL ceiling; flag-gating; import-guard for excluded services |
| contract | Tier 1 | spool column schema parity (7 services × 2 paths); env-contract 4 new vars; downtime namespace confirm |
| integration | Tier 1 | flag=false regression (7); flag=true row-set parity (7); downtime migration; spool lifecycle |
| data-boundary | Tier 1 | seam off-by-one; rn=start_row and rn=end_row inclusive; tie-stability per per-service ORDER BY key |
| resilience | Tier 1 + Tier 3 | partial-chunk Oracle error in Tier 1 (mock boundary); concurrent-insert consistency in Tier 3 (real infra) |
| stress | Tier 4 | parallel-execution peak RSS on production_history and resource_dataset — weekly gate |
| soak | Tier 4 | 24 h workload: memory uniformity, spool TTL respected, cleanup paths fire — weekly gate |

## Test Names

**`tests/test_batch_query_engine.py`** — extend, add after `TestDecomposeByTimeRange`:
- `TestDecomposeByRowCount::test_total_rows_zero_returns_empty`
- `TestDecomposeByRowCount::test_total_less_than_chunk_returns_single_range`
- `TestDecomposeByRowCount::test_total_exact_multiple_yields_n_chunks`
- `TestDecomposeByRowCount::test_total_rows_one`
- `TestDecomposeByRowCount::test_no_gap_no_overlap_property` (hypothesis over total_rows 1..1_000_000, chunk 1..200_000)
- `TestDecomposeByRowCount::test_ranges_are_1based_inclusive`
- `TestEngineParallelCeiling::test_hold_engine_parallel_capped_at_db_slow_pool_size`
- `TestEngineParallelCeiling::test_job_engine_parallel_capped`
- `TestEngineParallelCeiling::test_msd_engine_parallel_capped`
- `TestEngineParallelCeiling::test_parallel_ceiling_within_limit_does_not_raise`
- `TestFlagGating::test_flag_false_does_not_call_count_sql`
- `TestFlagGating::test_flag_true_calls_count_then_paged_sql`
- `TestExcludedServicesUnmodified::test_yield_alert_not_imported_by_batch_engine`
- `TestExcludedServicesUnmodified::test_material_trace_not_imported_by_batch_engine`

**`tests/test_downtime_analysis_service.py`** — extend:
- `TestDowntimeMigration::test_uses_batch_query_engine_not_direct_oracle`
- `TestDowntimeMigration::test_spool_namespace_unchanged`
- `TestDowntimeMigration::test_spool_column_schema_matches_previous_path`
- `TestDowntimeMigration::test_execute_plan_merge_chunks_to_spool_called`

**`tests/integration/test_rowcount_flag_parity.py`** — new file (Oracle mocked at `read_sql_df` boundary):
- `TestFlagFalseRegression::test_production_history_flag_false_row_identical`
- `TestFlagFalseRegression::test_reject_dataset_flag_false_row_identical`
- `TestFlagFalseRegression::test_resource_dataset_flag_false_row_identical`
- `TestFlagFalseRegression::test_hold_dataset_flag_false_row_identical`
- `TestFlagFalseRegression::test_job_query_flag_false_row_identical`
- `TestFlagFalseRegression::test_mid_section_defect_flag_false_row_identical`
- `TestFlagFalseRegression::test_downtime_analysis_flag_false_row_identical`
- `TestFlagTrueParity::test_production_history_flag_true_same_rowset`
- `TestFlagTrueParity::test_reject_dataset_flag_true_same_rowset`
- `TestFlagTrueParity::test_resource_dataset_flag_true_same_rowset`
- `TestFlagTrueParity::test_hold_dataset_flag_true_same_rowset`
- `TestFlagTrueParity::test_job_query_flag_true_same_rowset`
- `TestFlagTrueParity::test_mid_section_defect_flag_true_same_rowset`
- `TestFlagTrueParity::test_downtime_analysis_flag_true_same_rowset`
- `TestSpoolSchemaParity::test_column_names_identical_all_seven_services`
- `TestSpoolLifecycle::test_ttl_unchanged_flag_true`
- `TestSpoolLifecycle::test_cleanup_fires_correctly_flag_true`

**`tests/stress/test_chunk_boundary.py`** — extend:
- `TestChunkSeam::test_rn_start_row_included`
- `TestChunkSeam::test_rn_end_row_included`
- `TestChunkSeam::test_no_row_duplicated_across_adjacent_chunks`
- `TestChunkSeam::test_no_row_dropped_at_adjacent_chunk_boundary`
- `TestChunkSeam::test_boundary_mid_logical_group_no_split_artifact` (fixture: same TRACKINTIMESTAMP straddles chunk boundary)
- `TestOrderByTieStability::test_production_history_tie_stable_across_chunks`
- `TestOrderByTieStability::test_reject_dataset_tie_stable`
- `TestOrderByTieStability::test_hold_dataset_tie_stable`
- `TestMemoryProfile::test_parallel_flag_true_peak_rss_within_budget` (Tier 4)

**`tests/integration/test_race_conditions.py`** — extend (Tier 3, real Oracle):
- `TestCountPagedConsistency::test_count_paged_mismatch_under_concurrent_insert`

**`tests/integration/test_oracle_error_path.py`** — extend (Tier 1, mock):
- `TestPartialChunkFailure::test_partial_chunk_oracle_error_no_partial_spool_written`

## Out of Scope

- `yield_alert_dataset_cache`, `material_trace_service`, `material_consumption_service` — AC-8 non-goals
- Frontend / Playwright E2E — no UI surface change; existing specs are regression guards with flag default-off
- New CI required gate — classifier is confirm-only; extend existing test suite only
- Visual review, monkey test, API contract tests — no endpoint shape change
- Real-Oracle Tier 1 parity — deferred to nightly Tier 3; Tier 1 mocks at `read_sql_df` boundary

## Notes

- Mock at Oracle/network boundary (`read_sql_df`, `execute_plan`); do NOT mock internal service methods.
- Flag-parity fixtures must include at least one case where a chunk boundary falls mid-logical-group (same TRACKINTIMESTAMP across two chunks) to distinguish aggregation key designs — see `MES Domain Semantics Notes` in CLAUDE.md.
- Per-kwarg assertion discipline: use `mock.assert_called_once()` + `call_args.kwargs[key] == value`; never `assert_called_once_with(...)` as exact whitelist.
- `TestDecomposeByRowCount` and `TestFlagFalseRegression` must be written before implementation and must fail in a clean repo clone — these are the TDD red tests.
- Stress and soak tests (Tier 4) are weekly manual gates; they do NOT block PR merge.
