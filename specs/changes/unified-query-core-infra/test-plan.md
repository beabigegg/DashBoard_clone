---
change-id: unified-query-core-infra
schema-version: 0.1.0
last-changed: 2026-06-18
risk: high
tier: 1
---

# Test Plan: unified-query-core-infra

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | tests/test_base_chunked_duckdb_job.py | Tier 0 (pre-merge) |
| AC-2 | unit | tests/test_base_chunked_duckdb_job.py | Tier 0 (pre-merge) |
| AC-3 (mock) | unit + resilience | tests/test_oracle_arrow_reader.py | Tier 0 (pre-merge) |
| AC-3 (real pool) | integration | tests/integration/test_oracle_arrow_pool_lifecycle.py | Tier 3 (nightly) |
| AC-4 | unit | tests/test_query_cost_policy.py | Tier 0 (pre-merge) |
| AC-5 | integration | tests/integration/test_oracle_arrow_pool_lifecycle.py | Tier 3 (nightly) |
| AC-6 | contract | tests/contract/test_env_duckdb_job_dir.py | Tier 0 (pre-merge) |
| AC-7 | unit | tests/test_query_cost_policy.py | Tier 0 (pre-merge) |
| AC-8 | data-boundary | tests/test_oracle_arrow_reader.py | Tier 0 (pre-merge) |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | Tier 0 (pre-merge, < 30s) | ChunkStrategy × reduction paths; 4-layer cost policy; no-new-dep import check |
| contract | Tier 0 (pre-merge) | Pin DUCKDB_JOB_DIR name AND default value (D4) across all three contract files |
| data-boundary | Tier 0 (pre-merge) | null RecordBatch, empty chunk, Oracle DATE UTC midnight, Oracle CHAR strip |
| resilience | Tier 0 (pre-merge, mocked) | Mid-chunk Oracle failure → finally:conn.close(); DuckDB write failure → temp cleanup |
| integration | Tier 3 (nightly, integration_real lane) | Real Oracle pool exhaustion+recovery; writer_lock concurrent-write correctness; job-temp TTL |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | `pytest --collect-only tests/test_oracle_arrow_reader.py tests/test_query_cost_policy.py tests/test_base_chunked_duckdb_job.py tests/contract/test_env_duckdb_job_dir.py` | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | `pytest tests/test_oracle_arrow_reader.py tests/test_query_cost_policy.py tests/test_base_chunked_duckdb_job.py tests/contract/test_env_duckdb_job_dir.py` | 1 | test-evidence.yml |
| changed-area | yes | `pytest tests/test_oracle_arrow_reader.py tests/test_query_cost_policy.py tests/test_base_chunked_duckdb_job.py tests/contract/test_env_duckdb_job_dir.py` | 1 | test-evidence.yml |
| contract | yes (env + data-shape affected) | `pytest tests/contract/` | 1 | test-evidence.yml |
| full | final/CI | `pytest tests/ -m "not integration_real"` | 1 | test-evidence.yml |
| integration | nightly only | `pytest tests/integration/test_oracle_arrow_pool_lifecycle.py -m integration_real` | 1 | test-evidence.yml |

## Test Scenarios Per AC

**AC-1 — ChunkStrategy dispatch and hook invocation order:**
- `test_run_invokes_hooks_in_order_time` / `_id_list` / `_row_count` / `_single`: 4 concrete subclass fixtures; assert pre_query → build_chunk_sql → chunk_to_duckdb → post_aggregate → progress_report sequence via mock hooks.

**AC-2 — Two reduction paths:**
- `test_multi_parquet_append_no_writer_lock`: `requires_cross_chunk_reduction=False`; mock DuckDB; assert independent parquet writes, no writer_lock acquisition.
- `test_single_duckdb_writer_lock_serialization`: `requires_cross_chunk_reduction=True`; assert all INSERT calls occur inside writer_lock; assert one job-temp DuckDB file used.

**AC-3 — OracleArrowReader connection discipline:**
- `test_chunk_iter_yields_record_batches`: mock `oracledb.SessionPool`; assert return type is `pyarrow.RecordBatch`.
- `test_conn_returned_via_finally_on_success`: assert `conn.close()` called after successful iteration.
- `test_conn_returned_via_finally_on_mid_chunk_error`: inject exception mid-chunk; assert `conn.close()` still called.
- `test_pool_not_created_at_import`: import module; assert pool attribute is None/unset before first `chunk_iter()` call (D3 fork-safety guard).

**AC-4 — 4-layer short-circuit:**
- `test_l0_spool_hit_returns_sync_overrides_all`: spool hit → SYNC even when always_async=True and date_span large.
- `test_l1_always_async_domain_returns_async`: no spool hit; always_async flag → ASYNC without evaluating L2/L3.
- `test_l2_date_span_over_threshold_returns_async`: not always_async; date_span ≥ threshold → ASYNC; L3 not invoked.
- `test_l3_rowcount_over_threshold_returns_async`: COUNT(*) ≥ 200k → ASYNC.
- `test_all_under_threshold_returns_sync`: all layers pass → SYNC.
- `test_deprecation_warning_on_async_day_threshold_env`: set a `*_ASYNC_DAY_THRESHOLD` env var; assert `DeprecationWarning` emitted.

**AC-5 — Job-temp lifecycle (integration_real, nightly):**
- `test_job_temp_created_and_deleted_on_success`: assert file exists during run, deleted after completion.
- `test_job_temp_deleted_on_mid_job_failure`: inject failure; assert temp file cleaned and conn.close() called.

**AC-6 — Env contract pin:**
- `test_duckdb_job_dir_in_env_contract_md`: parse env-contract.md; assert row present.
- `test_duckdb_job_dir_in_env_example_template`: grep `.env.example.template`.
- `test_duckdb_job_dir_default_matches_d4`: parse `env.schema.json`; assert default == `{QUERY_SPOOL_DIR}/../duckdb_jobs`.

**AC-7 — No new deps, diff confined:**
- `test_no_pandas_import_in_new_modules`: `ast.parse()` + walk `ast.Call`/`ast.Import` on each new module file; assert no pandas node.
- `test_no_caller_outside_tests`: assert `src/` grep for the 3 new module names returns zero matches.

**AC-8 — Data-boundary:**
- `test_empty_chunk_yields_no_batches`: empty Oracle result → iterator yields nothing, no error.
- `test_null_fields_passthrough`: RecordBatch with null values → passed through without error or row loss.
- `test_oracle_date_midnight_no_tz_shift`: Oracle DATE 00:00:00 → assert no ±8h shift (regex H/M/S before conversion per frontend-patterns.md note).
- `test_oracle_char_strip_applied_at_boundary`: CHAR-padded column → assert `.strip()` applied.

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| (none) | — | pure new-module addition; no existing behavior changed (AC-7) |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- E2E tests (no HTTP endpoints, no UI surface)
- Stress/soak (deferred to first P1 domain migration per change-classification.md)
- Frontend tests (diff confined to `core/` + contracts + tests)
- Monkey/fuzz tests (no interactive surface)

## Notes

Integration tests require `pytestmark = pytest.mark.integration_real` and run nightly only — NOT in pre-merge targeted/changed-area phases (project test-layer governance). Pool fork-safety test (`test_pool_not_created_at_import`) is the only guard against D3 regression (ADR-0004). AC-6 default value must exactly match D4: `{QUERY_SPOOL_DIR}/../duckdb_jobs`. AC-7 no-new-dep check uses `ast.parse()` (import-alias-proof), per test-discipline.md.
