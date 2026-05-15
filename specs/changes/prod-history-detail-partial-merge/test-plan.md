---
change-id: prod-history-detail-partial-merge
schema-version: 0.1.0
last-changed: 2026-05-15
risk: medium
tier: 2
---

# Test Plan: prod-history-detail-partial-merge

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | test name(s) | tier |
|---|---|---|---|---|
| AC-1 | unit | `tests/test_production_history_sql_runtime.py` | `test_partial_merge_sum_qty_max_time`, `test_partial_count_equals_group_size` | 0 |
| AC-1 | unit | `tests/test_production_history_service.py` | `test_pandas_fallback_sum_qty_max_time`, `test_pandas_fallback_partial_count` | 0 |
| AC-2 | unit | `tests/test_production_history_sql_runtime.py` | `test_aba_interleave_not_merged` | 0 |
| AC-2 | unit | `tests/test_production_history_service.py` | `test_pandas_aba_interleave_not_merged` | 0 |
| AC-3 | unit | `tests/test_production_history_service.py` | `test_strict_guard_fallback_to_raw_rows`, `test_strict_guard_logs_summary_with_divergent_count` | 0 |
| AC-3 | unit | `tests/test_production_history_sql_runtime.py` | `test_duckdb_strict_guard_fallback_to_raw_rows` | 0 |
| AC-4 | unit | `tests/test_production_history_sql_runtime.py` | `test_pagination_total_rows_is_post_aggregation_count` | 0 |
| AC-4 | contract | `tests/test_api_contract.py` | `test_production_history_detail_pagination_total_rows_post_aggregation` | 1 |
| AC-5 | integration | `tests/test_production_history_sql_runtime.py` | `test_csv_rows_match_api_rows_aggregated`, `test_csv_partial_count_matches_api` | 1 |
| AC-6 | unit | `tests/test_production_history_sql_runtime.py` | `test_detail_row_includes_partial_count_field` | 0 |
| AC-6 | contract | `tests/test_api_contract.py` | `test_detail_row_schema_has_partial_count_integer` | 1 |
| AC-6 | unit | `frontend/tests/legacy/production-history.test.js` | `test partial_count badge renders when value gt 1`, `test partial_count badge absent when value equals 1` | 0 |
| PH-06 parity | integration | `tests/test_production_history_sql_runtime.py` | `test_duckdb_pandas_parity_aggregation_output` | 1 |
| PH-07 log | unit | `tests/test_production_history_service.py` | `test_strict_guard_logs_summary_with_divergent_count` | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | aggregation key correctness, MAX/SUM math, strict guard, partial_count, ABA non-merge, badge rendering |
| contract | 1 | `partial_count` field presence in API response schema; `pagination.total_rows` = post-aggregation count |
| integration | 1 | DuckDB SQL path vs pandas fallback produce identical output (parity); CSV export rows 1:1 match API rows |
| e2e | informational | existing `tests/e2e/test_production_history_e2e.py` runs as regression gate only; no new e2e specs |

## Test Files

- `tests/test_production_history_sql_runtime.py` — **extend**: add `TestPartialMergeAggregation` class covering AC-1 (DuckDB path), AC-2 (ABA), AC-4 (pagination count), AC-5 (CSV parity), AC-6 (field presence), PH-06 parity
- `tests/test_production_history_service.py` — **extend**: add `TestPandasFallbackAggregation` class covering AC-1 (pandas path), AC-2 (pandas ABA), AC-3 (strict guard + caplog INFO assertion)
- `tests/test_api_contract.py` — **extend**: add two assertions under existing production-history contract section for AC-4 and AC-6
- `frontend/tests/legacy/production-history.test.js` — **extend**: add badge rendering tests for AC-6

## Out of Scope

- data-boundary tests (5-key combination space covered by unit fixtures)
- resilience tests (no new failure mode introduced)
- monkey / fuzz tests
- stress tests (`tests/stress/test_production_history_stress.py` — Tier 2 exclusion)
- soak tests
- new Playwright e2e specs (existing `tests/e2e/test_production_history_e2e.py` runs informational regression)

## Notes

- AC-3 unit tests MUST use `pytest`'s `caplog` fixture (or `assertLogs`) to verify a SINGLE INFO log line per request with format `"partial-trackout strict-guard: <N> divergent groups fell back to raw rows ..."` where `N` matches the number of divergent groups; absence of the log line when divergence exists must fail the test; presence of the log line when `N==0` must also fail.
- PH-06 parity test (`test_duckdb_pandas_parity_aggregation_output`) uses a synthetic parquet fixture in a temp dir (pattern from `tests/test_msd_duckdb_parity.py`) — no Oracle or Redis dependency.
- AC-5 CSV parity test should assert `len(csv_rows) == len(api_rows)` and spot-check `partial_count` per row, not full JSON equality, to stay resilient to column order changes.
- All new Python tests must pass under `pytest` in the `mes-dashboard` conda env (`conda run -n mes-dashboard pytest`); no new env vars required.
- TDD order: write failing unit tests for AC-1/AC-2/AC-3 first; parity + contract tests after both paths are implemented.
