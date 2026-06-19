---
change-id: eap-alarm-unified-job-poc
schema-version: 0.1.0
last-changed: 2026-06-19
risk: high
tier: 1
---

# Test Plan: eap-alarm-unified-job-poc

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (schema+rowcount+row-set parity, mock-seam unit) | unit | tests/test_eap_alarm_service.py | 1 |
| AC-1 (parquet diff, flag ON vs OFF, real paths) | integration | tests/integration/test_eap_alarm_rq_async.py | 1 |
| AC-2 (base sink writes per-chunk parquet; no dup/loss) | unit | tests/test_base_chunked_duckdb_job.py | 1 |
| AC-2 (chunk seam: SET chunk-1, CLEAR chunk-2 → paired) | unit | tests/test_eap_alarm_service.py | 1 |
| AC-2 (no-dup/no-loss under parallel load) | stress | tests/stress/test_chunk_boundary.py | 1 |
| AC-3 (parallel wall-time lower; memory not linear) | stress | tests/stress/test_async_job_stress.py | 1 |
| AC-4 (forced-sync 503, no silent downgrade) | unit | tests/test_async_query_job_service.py | 1 |
| AC-5 (unified enqueue replaces Pattern A+B, exposes flags) | unit | tests/test_async_query_job_service.py | 1 |
| AC-6 (conn returned via finally; no leak on fault) | integration | tests/integration/test_eap_alarm_resilience.py | 1 |
| AC-6 (pool size unchanged after N eap_alarm jobs) | integration | tests/integration/test_oracle_arrow_pool_lifecycle.py | 1 |
| AC-6 (sustained soak, no leak, bounded memory) | soak | tests/integration/test_soak_workload.py | 1 |
| AC-7 (env default pin off/false) | contract | tests/contract/test_env_eap_alarm_flag.py | 1 |
| AC-8 (flag-OFF rowcount identical to legacy) | integration | tests/integration/test_rowcount_flag_parity.py | 1 |
| AC-8 (flag-OFF parquet byte-for-row matches legacy snapshot) | integration | tests/integration/test_eap_alarm_rq_async.py | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 1 | `test_base_chunked_duckdb_job.py`, `test_eap_alarm_service.py`, `test_async_query_job_service.py` — targeted phase, pre-merge |
| contract | 1 | `tests/contract/test_env_eap_alarm_flag.py` (new file) — contract phase, pre-merge |
| integration | 1 | `test_eap_alarm_rq_async.py`, `test_eap_alarm_data_boundary.py`, `test_eap_alarm_resilience.py`, `test_oracle_arrow_pool_lifecycle.py`, `test_rowcount_flag_parity.py` — changed-area phase, pre-merge; `@pytest.mark.integration_real` subtests run nightly |
| data-boundary | 1 | `test_eap_alarm_data_boundary.py` — extend with spool schema+rowcount consistency |
| resilience | 1 | `test_eap_alarm_resilience.py` — chunk fault injection, no partial-result corruption |
| e2e | 1 | `tests/e2e/test_eap_alarm_e2e.py` — flag-ON E2E parity + coarse progress tolerated; requires Playwright + GunicornHarness |
| stress | 1 | `tests/stress/test_async_job_stress.py`, `tests/stress/test_chunk_boundary.py` — NOT pre-merge; weekly/manual CI workflow |
| soak | 1 | `tests/integration/test_soak_workload.py` — NOT pre-merge; weekly CI workflow |

## Test Functions to ADD or EXTEND

**tests/test_base_chunked_duckdb_job.py** — extend `TestReductionPaths` (currently `test_false_reduction_path_no_writer_lock` only records calls; no parquet write asserted):
- `test_fan_out_append_writes_per_chunk_parquet` — `requires_cross_chunk_reduction=False` path: each chunk batch lands in `chunk-{idx}-{batch}.parquet` under `_make_chunk_parquet_dir(job_id)`
- `test_fan_out_append_parallel_no_file_collision` — parallel chunks write distinct file names; no overwrite
- `test_fan_out_append_seam_fixture` — two-chunk mock: SET in chunk-1, CLEAR in chunk-2; `post_aggregate` glob must see both rows (cross-seam base-sink correctness, AC-2)
- `test_make_chunk_parquet_dir_creates_namespace_dir` — helper returns `{DUCKDB_JOB_DIR}/{namespace}/{job_id}/` and creates it
- `test_fan_out_append_empty_chunk_leaves_dir_present` — zero-batch chunk does not crash; dir present after

**tests/test_eap_alarm_service.py** — extend (current coverage: spool key, date validation, alarm-category decode, schema-version pin; nothing tests `EapAlarmJob`):
- `test_eap_alarm_job_inherits_base` — `EapAlarmJob.namespace`, `chunk_strategy`, `requires_cross_chunk_reduction`, `max_parallel` match design spec
- `test_pre_query_emits_daily_chunk_pairs` — 3-day range → 6 chunk descriptors (3 windows × 2 kinds: events+detail); each has `kind` + date-window binds
- `test_build_chunk_sql_events_kind` — returns events SQL + correct binds for a single window
- `test_build_chunk_sql_detail_kind` — returns detail SQL + correct binds
- `test_post_aggregate_pairs_cross_seam` — mock parquet glob: SET event in events-chunk-1, CLEAR event in events-chunk-2; output has one paired row with valid `ALARM_START`+`ALARM_END` (AC-1, D6 parity template)
- `test_progress_report_calls_update_job_progress` — four-call sequence 5→15→90→100 maps to `update_job_progress` calls (AC-3 R3 coarse bracket)

**tests/test_async_query_job_service.py** — extend (current coverage: `enqueue_job`, `get_job_status`, `update_job_progress`, `complete_job`, multi-stage progress; no `enqueue_query_job`):
- `test_enqueue_query_job_returns_202_when_async_available` — `always_async=True` + available → `(job_id, None, 202)` result
- `test_enqueue_query_job_503_when_always_async_unavailable_no_fallback` — `always_async=True` + unavailable + `sync_fallback_allowed=False` → `(None, error, 503)`; no RQ enqueue call (AC-4)
- `test_enqueue_query_job_no_sync_downgrade` — on 503 path: `enqueue_job` / `enqueue_job_dynamic` never called (AC-4 silent-downgrade guard)
- `test_enqueue_query_job_sync_fallback_when_allowed` — `always_async=False` + unavailable + `sync_fallback_allowed=True` → sync-fallback outcome (non-eap domain path; proves flag semantics)
- `test_enqueue_query_job_replaces_pattern_a_and_b` — `enqueue_query_job` callable exists and accepts `always_async`/`sync_fallback_allowed` kwargs; eap-alarm registered with `always_async=True` (AC-5)

**tests/contract/test_env_eap_alarm_flag.py** — new file (model: `test_env_duckdb_job_dir.py` which has three test classes covering contract-md, .env.example, and env.schema.json):
- `test_eap_alarm_use_unified_job_documented_in_env_contract` — `EAP_ALARM_USE_UNIFIED_JOB` string present in `contracts/env/env-contract.md`
- `test_eap_alarm_use_unified_job_default_is_off` — env-contract prose contains default `off` or `false` (AC-7 pin)
- `test_eap_alarm_use_unified_job_in_env_example` — flag line present in `.env.example`
- `test_eap_alarm_use_unified_job_in_env_schema` — property present in `contracts/env/env.schema.json`
- `test_eap_alarm_use_unified_job_schema_default_is_false` — schema property default equals `false`/`"off"` (AC-7 pin)

**tests/integration/test_eap_alarm_rq_async.py** — extend `TestEapAlarmWorkerFn` (currently tests `run_eap_alarm_query_job` only):
- `test_flag_on_vs_off_parquet_schema_identical` — same seeded batches: flag ON and OFF produce identical parquet column names+types (AC-1)
- `test_flag_on_vs_off_rowcount_identical` — same rowcount (AC-1)
- `test_flag_on_vs_off_business_key_rowset_identical` — `(EQP_ID, ALARM_ID, ALARM_START)` set equality, order-insensitive (AC-1/D6)
- `test_flag_off_parquet_matches_pre_change_baseline` — flag OFF result matches pre-seeded snapshot (AC-8)

**tests/integration/test_eap_alarm_data_boundary.py** — extend (currently: data-boundary tests for spool views; no parity tests):
- `test_spool_parquet_schema_unchanged_across_paths` — unified-job spool has same column set as legacy spool (data-boundary parity)
- `test_spool_rowcount_consistent_across_runs_flag_on` — same params → same rowcount on two `EapAlarmJob` runs (idempotency)

**tests/integration/test_eap_alarm_resilience.py** — extend (currently: Oracle failure, Redis failure, spool-miss 410, inflight-abort):
- `test_chunk_fault_injection_no_partial_spool` — one chunk raises `OracleError` during parallel fan-out; spool file NOT written (no partial registration)
- `test_chunk_fault_injection_sibling_connections_released` — when one chunk fails, sibling chunk connections are returned to pool (AC-6 `finally` path)

**tests/integration/test_oracle_arrow_pool_lifecycle.py** — extend `TestJobTempLifecycle` (currently: temp-lifecycle, mid-job error for reduction path):
- `test_eap_alarm_job_no_connection_leak_sustained` — run N `EapAlarmJob` instances sequentially/concurrently; pool `maxsize` unchanged after all complete (AC-6 sustained)

**tests/integration/test_rowcount_flag_parity.py** — extend `TestFlagFalseRegression` (currently covers production_history, hold, reject, resource, job, msd, downtime):
- `test_eap_alarm_flag_off_uses_legacy_worker` — flag OFF routes to `run_eap_alarm_query_job`, not `EapAlarmJob`; rowcount matches legacy mock baseline (AC-8)

**tests/e2e/test_eap_alarm_e2e.py** — extend `TestEapAlarmSpoolE2E` (currently: 202 async, views, pagination; no flag-ON path):
- `test_eap_alarm_flag_on_e2e_result_set_identical` — with flag ENV=on, spool+poll returns same `(EQP_ID, ALARM_ID)` set as flag-OFF baseline (AC-1/AC-3 E2E)
- `test_eap_alarm_progress_coarse_bracket_tolerated` — poller observes 5/15/90/100 progress stages (not legacy 6-stage); page renders without error (R3)

**tests/stress/test_async_job_stress.py** — extend (add eap-alarm class alongside existing `TestProductionHistoryQueueSaturation`):
- `test_eap_alarm_5_concurrent_unified_jobs` — 5 concurrent `EapAlarmJob` fan-outs complete without queue starvation or pool exhaustion (AC-3/AC-6)

**tests/stress/test_chunk_boundary.py** — extend `TestChunkSeam` (currently: row-number boundary; no daily-seam tests):
- `test_eap_alarm_daily_seam_no_row_duplicated` — events straddling midnight appear exactly once in final spool (AC-2/R2)
- `test_eap_alarm_daily_seam_no_row_dropped` — every event in the full range appears in the spool after chunking (AC-2)

**tests/integration/test_soak_workload.py** — extend (currently tests other domains; add eap-alarm soak):
- `test_eap_alarm_soak_no_connection_leak` — sustained eap_alarm async load over time; pool size bounded; no memory-peak linear growth (AC-6/AC-3 soak)

## Test Execution Ladder

| phase | required | scope | max failures |
|---|---|---|---|
| collect | yes | all files in AC→Test Mapping table | 1 |
| targeted | yes | tests/test_eap_alarm_service.py, tests/test_base_chunked_duckdb_job.py, tests/test_async_query_job_service.py | 1 |
| changed-area | yes | tests/integration/test_eap_alarm_rq_async.py, tests/integration/test_eap_alarm_data_boundary.py, tests/integration/test_eap_alarm_resilience.py, tests/integration/test_oracle_arrow_pool_lifecycle.py, tests/integration/test_rowcount_flag_parity.py, tests/e2e/test_eap_alarm_e2e.py | 1 |
| contract | yes | `cdd-kit validate` + tests/contract/test_env_eap_alarm_flag.py | 1 |
| quality | yes | `ruff check` on all modified/new files | 1 |
| full | final/CI | full pytest suite | 1 |
| stress/soak | weekly/manual | tests/stress/test_async_job_stress.py, tests/stress/test_chunk_boundary.py, tests/integration/test_soak_workload.py | 1 |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_base_chunked_duckdb_job.py::TestReductionPaths::test_false_reduction_path_no_writer_lock | update | currently records calls only; must assert parquet files written per batch (IP-1 base sink) |
| tests/integration/test_eap_alarm_rq_async.py::TestEapAlarmWorkerFn::test_worker_fn_progress_milestones | update | legacy 6-stage milestones; coarse 4-point bracket (5/15/90/100) is accepted target after EapAlarmJob lands (R3) |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- Frontend eap_alarm pages (view layer; no change)
- Other domains (production, reject, resource, material_trace, downtime)
- Spool parquet schema change (`_SCHEMA_VERSION` bump — explicit non-goal, ADR-0008)
- Removing legacy `run_eap_alarm_query_job` (deferred to P4/P5)
- `enqueue_job` / `enqueue_job_dynamic` internal refactor (no-touch per implementation-plan)

## Notes

- D6 seam fixture (SET in chunk-1, CLEAR in chunk-2) is the acceptance gate for IP-5 "done"; must exist before EapAlarmJob is declared complete.
- `enqueue_query_job` return shape `(job_id|None, error|None, http_status)` must be locked in `test_async_query_job_service.py` before IP-6 (route) consumes it.
- stress/soak tests are NOT pre-merge; they run in a separate weekly/manual CI workflow and produce `stress-soak-report.md`.
- AC-8 (flag-OFF zero-regression) is a standing gate for the entire P1–P4/P5 coexistence window, not just this PR.
- `tests/contract/test_env_eap_alarm_flag.py` is a new file; model it on `tests/contract/test_env_duckdb_job_dir.py`.
