---
change-id: downtime-duckdb-join-migration
schema-version: 0.1.0
last-changed: 2026-06-19
risk: high
tier: 1
---

# Test Plan: downtime-duckdb-join-migration

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 flag-off zero-regression | integration | `tests/integration/test_rowcount_flag_parity.py::TestFlagFalseRegression::test_downtime_analysis_flag_false_uses_execute_plan` | 0 |
| AC-2 no pd.merge in flag-on path | unit | `tests/test_downtime_unified_job.py::TestDowntimeJobPostAggregate::test_bridge_join_runs_in_duckdb_no_pd_merge` | 0 |
| AC-3 flag-on/off full row-set equivalence | integration | `tests/integration/test_downtime_rq_async.py::TestDowntimeFlagParity::test_flag_on_off_spool_row_set_equal` | 1 |
| AC-4 SINGLE per group, no TIME/ROW_COUNT chunking | unit | `tests/test_downtime_unified_job.py::TestDowntimeJobPreQuery::test_chunk_strategy_single_per_resourceid_group` | 0 |
| AC-5 OOM ceiling — high-cardinality RESOURCEID join | stress | `tests/stress/test_downtime_analysis_stress.py::TestDowntimeUnifiedJobOomCeiling::test_high_cardinality_join_no_heap_oom` | 3 |
| AC-5 OOM ceiling — single hot RESOURCEID spill bound | stress | `tests/stress/test_downtime_analysis_stress.py::TestDowntimeUnifiedJobOomCeiling::test_single_hot_resourceid_spill_bounds_rss` | 3 |
| AC-6 env-contract name + default off pinned | contract | `tests/contract/test_env_downtime_unified_flag.py::TestDowntimeUnifiedFlagInEnvSchema::test_flag_default_off_pinned` | 0 |
| AC-6 env-contract in all three contract files | contract | `tests/contract/test_env_downtime_unified_flag.py` | 0 |
| AC-7 winner-selection + 80% ambiguity flag | unit | `tests/test_downtime_unified_job.py::TestDowntimeJobPostAggregate::test_match_ambiguous_true_when_runner_up_gte_80pct` | 0 |
| AC-7 cross-shift 60s-gap merge (both directions) | unit | `tests/test_downtime_unified_job.py::TestDowntimeJobPostAggregate::test_cross_shift_merge_60s_gap_both_directions` | 0 |
| AC-7 orphan event — no job match | unit | `tests/test_downtime_unified_job.py::TestDowntimeJobPostAggregate::test_orphan_event_no_job_match` | 0 |
| AC-7 Path-A direct JOBID equi-join | unit | `tests/test_downtime_unified_job.py::TestDowntimeJobPostAggregate::test_path_a_direct_jobid_equijoin` | 0 |
| AC-8 no spool schema change / no e2e regression | e2e | `tests/e2e/test_downtime_analysis_e2e.py::TestFeatureFlagFallback::test_flag_off_returns_legacy_shape` | 0 |
| AC-8 spool key invariant between paths | unit | `tests/test_downtime_unified_job.py::TestDowntimeJobSpoolKey::test_spool_key_identical_between_paths` | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | `tests/test_downtime_unified_job.py` (new). Mock `OracleArrowReader.chunk_iter` with fixed Arrow batches. Classes: `TestDowntimeJobPreQuery`, `TestDowntimeJobChunkToDb`, `TestDowntimeJobPostAggregate`, `TestDowntimeFlagDispatch`, `TestDowntimeJobSpoolKey`. Covers AC-2, AC-4, AC-7, AC-8. |
| contract | 0 | `tests/contract/test_env_downtime_unified_flag.py` (new, three-class pattern matching `test_env_material_trace_flag.py`). Pins `DOWNTIME_USE_UNIFIED_JOB` name + default `off` across env-contract.md, env.schema.json, .env.example. Covers AC-6. |
| data-boundary | 0 | Inside `tests/test_downtime_unified_job.py::TestDowntimeJobPostAggregate`: NULL time-window rows, empty RESOURCEID group, overlap tiebreak (CREATEDATE ASC then JOBID ASC). |
| cost-policy | 0 | `tests/test_query_cost_policy.py` — add `downtime_worker` to `_APPROVED_CALLERS` for both `oracle_arrow_reader` and `base_chunked_duckdb_job`. `tests/test_job_registry.py` job-type count +1. |
| integration | 1 | Extend `tests/integration/test_rowcount_flag_parity.py` (AC-1 flag-off path unchanged). Extend `tests/integration/test_downtime_rq_async.py` with `TestDowntimeFlagParity` (AC-3 full row-set equality, `integration_real` marker). Nightly gate; deferred from pre-merge. |
| resilience | 1 | Extend `tests/integration/test_downtime_rq_async.py`: Oracle chunk-fault → no spool registered; worker restart mid-job → 410; DuckDB spill under constrained RSS completes. Nightly gate. |
| e2e | 1 | `tests/e2e/test_downtime_analysis_e2e.py` existing tests must pass with flag default off (AC-8). No new tests unless a regression gap is found. |
| stress | 3 | Extend `tests/stress/test_downtime_analysis_stress.py` with `TestDowntimeUnifiedJobOomCeiling`. Weekly / manual; not in pre-merge floor. |
| soak | 4 | `tests/integration/test_soak_workload.py` (if exists) — extend for downtime unified job. Weekly. |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | cdd-kit test select | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | cdd-kit test select | 1 | test-evidence.yml |
| changed-area | yes | cdd-kit test select | 1 | test-evidence.yml |
| contract | if affected | cdd-kit validate --contracts | 1 | test-evidence.yml |
| quality | if configured | ci-gates.md | 1 | test-evidence.yml |
| full | final/CI | cdd-kit test run --phase full | 1 | test-evidence.yml |

Pre-merge floor (collect + targeted + changed-area + contract):
- collect: `tests/test_downtime_unified_job.py`, `tests/integration/test_rowcount_flag_parity.py`, `tests/contract/test_env_downtime_unified_flag.py`, `tests/test_query_cost_policy.py`, `tests/test_job_registry.py`
- targeted: `tests/test_downtime_unified_job.py`
- changed-area: `tests/test_downtime_unified_job.py`, `tests/integration/test_rowcount_flag_parity.py`, `tests/e2e/test_downtime_analysis_e2e.py`, `tests/test_base_chunked_duckdb_job.py`, `tests/test_job_registry.py`, `tests/test_query_cost_policy.py`
- contract: `cdd-kit validate --contracts` + `tests/contract/test_env_downtime_unified_flag.py`

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/integration/test_rowcount_flag_parity.py::TestFlagFalseRegression::test_downtime_analysis_flag_false_uses_execute_plan` | extend | Add assertion that legacy `execute_downtime_query_job` path is invoked when `DOWNTIME_USE_UNIFIED_JOB=off` |
| `tests/integration/test_downtime_rq_async.py` | extend | Add `TestDowntimeFlagParity` class for AC-3 full row-set parity and resilience cases |
| `tests/stress/test_downtime_analysis_stress.py` | extend | Add `TestDowntimeUnifiedJobOomCeiling` class for AC-5 |
| `tests/test_query_cost_policy.py` | edit | Add `downtime_worker` to both `_APPROVED_CALLERS` dicts |
| `tests/test_job_registry.py` | edit | Bump expected `register_job_type()` count by 1 |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- `query_downtime_dataset_raw` two-spool / DuckDB-WASM browser-bridge path (design D6)
- ADR-0003 BQE ROW_COUNT chunking exclusion (existing coverage in `test_rowcount_flag_parity.py`)
- Frontend downtime pages and CSS (no UI surface; spool schema unchanged)
- `BaseChunkedDuckDBJob` named-target-table generalization (future work; override is local to `DowntimeJob`)
- Spool key, `_SCHEMA_VERSION`, view endpoints, API response shape (explicit non-goals per design D6)

## Notes

- AC-3 parity MUST be full row-set equality on `(event_id, job_id, match_source)` — not schema+count only (design D5). Count-only passes while silently regressing on winner-selection or the 80% ambiguity flag.
- AC-7 `test_match_ambiguous_true_when_runner_up_gte_80pct` is the ADR-0010 guard: if bridge_join.sql is ever simplified to ASOF JOIN this test must fail red.
- AC-5 stress tests are Tier 3 (weekly/manual) and do NOT block pre-merge.
- `tests/contract/test_env_downtime_unified_flag.py` must follow the three-class structure of `test_env_material_trace_flag.py` (InEnvContract, InEnvExample, InEnvSchema).
- `pip install jsonschema` required before `cdd-kit validate --contracts` in CI (CLAUDE.md learning).
