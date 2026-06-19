---
change-id: production-reject-history-migration
schema-version: 0.1.0
last-changed: 2026-06-19
risk: medium
tier: 1
---

# Test Plan: production-reject-history-migration

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (ProductionHistoryJob spool parity) | unit + data-boundary | `tests/test_production_history_unified_job.py` | 0 |
| AC-2 (RejectHistoryJob DuckDB groupby/pareto/trend parity) | unit + data-boundary | `tests/test_reject_history_unified_job.py` | 0 |
| AC-3 (feature flags default off; legacy path executes on flag=off) | unit | `tests/test_production_history_unified_job.py`, `tests/test_reject_history_unified_job.py` | 0 |
| AC-4 (OOM guard removal — ast absence proof) | contract | `tests/test_reject_history_unified_job.py` | 0 |
| AC-5 (RSS pandas fallback removal — ast absence proof) | contract | `tests/test_production_history_routes.py` | 0 |
| AC-6 (job_registry registration, always_async=False) | unit | `tests/test_async_query_job_service.py` | 0 |
| AC-7 (_APPROVED_CALLERS extended for both new workers) | contract | `tests/test_query_cost_policy.py` | 0 |
| AC-8 (view endpoints shape unchanged; Playwright specs pass under both flag states) | e2e | `tests/e2e/test_production_history_e2e.py`, `tests/e2e/test_reject_history_e2e.py` | 1 |
| AC-1 + AC-2 (RQ-async spool parity under real worker process) | integration | `tests/integration/test_production_history_rq_async.py`, `tests/integration/test_reject_history_rq_async.py` | 3 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Job constructor, `run()`, chunk dispatch, flag branch routing |
| data-boundary | 0 | Parity fixtures: NULL equipment, empty chunk windows, multi-defect lots, multi-reason trend |
| contract | 0 | ast-walk absence proofs (OOM guards, pandas fallback); _APPROVED_CALLERS membership; registry shape |
| integration | 3 (nightly) | RQ worker spool write + view-endpoint read-back; mock at Oracle/Redis network boundary |
| e2e | 1 | Existing Playwright specs pass unmodified; re-run under flag=on via env override |
| stress | 3 (nightly) | Extend existing stress files; no new stress files needed |

## Parity Test Strategy (AC-1, AC-2)

**Production History (AC-1):** after `ProductionHistoryJob.run()` merges chunks, read spool via
existing spool store; assert row-level equality (sorted on primary key) with legacy path output.
Schema columns must match exactly — no added or dropped fields.

**Reject History (AC-2):** numeric tolerance `abs(legacy - duckdb) ≤ 1e-6` for float qty/yield
fields; integer aggregation fields must be bit-exact. Mandatory fixture rows:
NULL `EQUIPMENT_ID` (must survive groupby), an all-zero chunk window (empty date range),
≥2 `DEFECT_CODE` values per lot (deterministic pareto order), ≥2 `REASON` categories (trend split).

**AC-4 OOM absence:** `ast.parse()` + `ast.walk()` over `reject_history_service.py` and
`reject_dataset_cache.py`; assert zero `ast.If` nodes whose body contains `ast.Raise` and whose
test is a `Compare` with `len(df)` or `df.memory_usage` as the left operand.

**AC-5 RSS fallback absence:** `ast.parse()` + `ast.walk()` over `production_history_routes.py`;
assert no module-level `import pandas` node and no string literal matching `SELECT \*` outside the
unified-job branch guard.

## Test Files

**New (create):**
- `tests/test_production_history_unified_job.py`
  - `test_flag_off_routes_to_legacy_service`
  - `test_flag_on_instantiates_production_history_job`
  - `test_production_history_job_spool_parity_exact_rows`
  - `test_production_history_job_empty_chunk_window_handled`
  - `test_production_history_job_progress_milestones`
- `tests/test_reject_history_unified_job.py`
  - `test_flag_off_routes_to_legacy_service`
  - `test_flag_on_instantiates_reject_history_job`
  - `test_reject_history_job_groupby_parity_null_equipment`
  - `test_reject_history_job_pareto_parity_multi_defect`
  - `test_reject_history_job_trend_parity_tolerance`
  - `test_reject_history_job_empty_chunk_window_no_crash`
  - `test_oom_guard_patterns_absent_in_reject_history_service`
  - `test_oom_guard_patterns_absent_in_reject_dataset_cache`
- `tests/integration/test_production_history_rq_async.py`
  - `test_production_history_job_enqueues_and_spool_readable`
  - `test_flag_off_spool_matches_flag_on_spool`
- `tests/integration/test_reject_history_rq_async.py`
  - `test_reject_history_job_enqueues_and_spool_readable`
  - `test_pareto_endpoint_shape_unchanged_under_unified_job`

**Extend (existing):**
- `tests/test_query_cost_policy.py::TestNoPandasAndNoCallers::test_no_caller_outside_tests`
  — add `production_history_worker` and `reject_history_worker` to `_APPROVED_CALLERS["base_chunked_duckdb_job"]`
- `tests/test_async_query_job_service.py`
  — `test_production_history_job_registered_always_async_false`
  — `test_reject_history_job_registered_always_async_false`
- `tests/test_production_history_routes.py`
  — `test_rss_pandas_fallback_branch_absent_in_ast`

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_query_cost_policy.py::TestNoPandasAndNoCallers::test_no_caller_outside_tests` | update | _APPROVED_CALLERS must include both new worker modules (AC-7) |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- No new frontend/Vue tests (AC-8 proven by existing Playwright specs)
- No Oracle live-data tests pre-merge (integration mocks at Oracle/Redis boundary)
- No new stress test files (extend existing `tests/stress/test_*_history_stress.py`)
- No soak tests (flat batch job, no state machine)
- CSS governance and i18n: no UI changes in this migration

## Notes

- Use `monkeypatch.setattr()` for feature-flag constants — they are frozen at import; `os.environ` setenv will not work.
- Check `pytestmark` in integration test files before adding mock-based tests; gate with `@pytest.mark.integration` only if the file already uses real infra.
- AC-7 (`test_no_caller_outside_tests`) is the intended pre-implementation trip-wire: it must fail red until both worker modules are wired to `BaseChunkedDuckDBJob`.
- Integration tests mock at network boundary (Oracle cursor, Redis); do not mock internal service methods.
