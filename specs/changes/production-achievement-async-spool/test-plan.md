---
change-id: production-achievement-async-spool
schema-version: 0.1.0
last-changed: 2026-07-08
risk: high
tier: 1
---

# Test Plan: production-achievement-async-spool

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | tests/test_production_achievement_routes.py::TestReportRoute::test_report_spool_miss_enqueues_returns_202_with_job_id | 0 |
| AC-1 | unit | tests/test_production_achievement_routes.py::TestReportRoute::test_report_route_never_calls_get_achievement_report_or_read_sql_df | 0 |
| AC-1 | unit | tests/test_production_achievement_unified_job.py::TestProductionAchievementJob::test_pre_query_builds_time_chunks_no_direct_read_sql_df | 0 |
| AC-2 | unit | tests/test_production_achievement_routes.py::TestReportRoute::test_spool_hit_response_shape_has_spool_download_url_spec_map_targets_map | 0 |
| AC-2 | unit | frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts::poll to completion downloads spool and renders rows | 0 |
| AC-2 | e2e | frontend/tests/playwright/production-achievement-async.spec.ts::long-span async flow: progress shows then results render | 2 |
| AC-3 | unit | tests/test_spool_routes.py::test_production_achievement_in_allowed_namespaces (extend test_allowed_namespaces_pass_namespace_validation parametrize list) | 0 |
| AC-3 | unit | tests/test_spool_routes.py::test_unknown_namespace_returns_400 (existing, reused as regression guard) | 0 |
| AC-3 | integration | tests/integration/test_production_achievement_rq_async.py::TestProductionAchievementSpoolDownload::test_authorized_client_streams_parquet | 1 |
| AC-4 | unit | tests/test_query_cost_policy.py::TestNoPandasAndNoCallers::test_no_caller_outside_tests (extend _APPROVED_CALLERS["base_chunked_duckdb_job"] with production_achievement_worker) | 0 |
| AC-4 | unit | tests/test_production_achievement_unified_job.py::TestProductionAchievementJob::test_always_async_registered, ::test_run_wraps_oracle_fanout_in_heavy_query_slot | 0 |
| AC-4 | unit | tests/test_job_registry.py::TestAlwaysAsyncField::test_production_achievement_registered_with_always_async_true (NEW method, mirrors test_eap_alarm_registered_with_always_async_true; does NOT bump the 12-count in TestJobServiceRegistrations) | 0 |
| AC-4 | stress | tests/stress/test_base_job_semaphore_stress.py (reused unmodified — domain-agnostic BaseChunkedDuckDBJob.run() coverage) | 4 |
| AC-5 | contract | tests/contract/test_env_production_achievement_unified_flag.py (NEW, mirror test_env_downtime_unified_flag.py) | 0 |
| AC-5 | contract | tests/test_env_contract.py::test_production_achievement_async_env_vars_pinned_defaults (NEW method, mirror test_resource_async_env_vars_pinned_defaults) | 0 |
| AC-5 | contract | tests/contract/test_env_production_achievement_unified_flag.py::TestGunicornWorkerParity::test_gunicorn_conf_and_rq_worker_preload_reference_same_flag_names | 0 |
| AC-6 | unit | tests/test_production_achievement_unified_job.py::TestSpoolSchema::test_parquet_columns_are_output_date_shift_code_specname_actual_output_qty, ::test_schema_version_constant_pinned | 0 |
| AC-6 | data-boundary | tests/integration/test_production_achievement_resilience.py::test_empty_qualifying_rows_writes_valid_empty_parquet_not_error | 1 |
| AC-7 | unit | tests/test_production_achievement_unified_job.py::TestChunkSeamReaggregation::test_midnight_seam_group_produces_one_row_not_duplicate_keys (KEY test — PA-03/PA-04 previous-day tail straddling a chunk seam) | 0 |
| AC-7 | unit | tests/test_production_achievement_unified_job.py::TestChunkSeamReaggregation::test_post_aggregate_sum_merges_same_key_across_chunks | 0 |
| AC-7 | integration | tests/integration/test_production_achievement_rq_async.py::TestUnifiedJobParity::test_worker_parquet_business_key_diff_vs_build_achievement_rows_golden (real-path parquet diff, pytest.mark.integration_real) | 1 |
| AC-7 | unit | tests/test_frontend_production_achievement_parity.py (NEW, mirror test_frontend_hold_history_parity.py — DuckDB-emulated PA-06 rollup + PA-07 target-join business-key diff vs build_achievement_rows() golden) | 0 |
| AC-7 | unit | tests/test_frontend_duckdb_parity.py::TestProductionAchievementRateParity::test_achievement_rate_formula_matches_backend (extend, subprocess against real frontend TS formula; add PA cases/metric_tolerance to tests/fixtures/frontend_compute_parity.json) | 0 |
| AC-7 | unit | frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts::rollup groups by workcenter_group, ::target join yields achievement_rate, ::missing target -> null rate, ::zero target -> null not Infinity, ::zero actual nonzero target -> 0.0, ::empty spool renders empty table not error | 0 |
| AC-8 | unit | frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts::activation policy called with threshold=0, always activates | 0 |
| AC-8 | unit | tests/test_production_achievement_routes.py::TestReportRoute::test_spool_hit_injects_download_url_unconditionally_not_row_count_gated | 0 |
| AC-9 | e2e | frontend/tests/playwright/production-achievement-async.spec.ts (full describe block: async flow, empty state, error state) | 2 |
| AC-9 | resilience | tests/integration/test_production_achievement_resilience.py::test_oracle_failure_during_spool, ::test_redis_failure_returns_503, ::test_job_timeout_produces_terminal_error_status, ::test_missing_spool_after_completion_returns_410 (mirror test_eap_alarm_resilience.py) | 1 |
| AC-9 | unit | deploy/mes-dashboard-production-achievement-worker.service structural convention check (owned by ci-cd-gatekeeper; e.g. tests/deploy/test_systemd_units.py if such a suite exists, else a NEW minimal parser test) | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Chunk-seam `post_aggregate` re-aggregation (KEY test), `_APPROVED_CALLERS`, always_async registration, spool schema/`_SCHEMA_VERSION`, `_ALLOWED_NAMESPACES`, route 202/200/503 branches (mock `is_async_available()` + enqueue fn — CI has no Redis), frontend DuckDB-WASM rollup/join/rate composable |
| contract | 0 | Env default/enum pin for 3 `PRODUCTION_ACHIEVEMENT_*` vars, gunicorn↔worker flag-name parity, response-sample re-capture (202 + 200 spool-hit shapes), `openapi.json`/`contracts/openapi.json` mirror resolution, `data-shape-contract.md` §3.28 schema coverage |
| integration | 1 | `tests/integration/test_production_achievement_rq_async.py` — `pytestmark = pytest.mark.integration_real` (nightly gate, matches every sibling `test_*_rq_async.py`); enqueue→job→spool round-trip, dual-tier parquet business-key diff, spool download by authorized client |
| e2e | 1-2 | `frontend/tests/playwright/production-achievement-async.spec.ts` (Playwright, browser DuckDB-WASM); GunicornHarness backend browser e2e reusing `tests/e2e/browser_helpers.py` |
| data-boundary | 1 | Empty/all-unmapped-SPECNAME window, malformed spool rows, missing targets row |
| resilience | 1 | `tests/integration/test_production_achievement_resilience.py` — worker crash (generic coverage from `tests/test_rq_worker_crash_recovery.py`), Redis down, job timeout, missing/late spool, unauthorized namespace |
| monkey | 1 | Operation-sequence spec instance from `tests/templates/monkey/operation-sequence.spec.md` — rapid poll/cancel/retry, navigate-away mid-poll, double-submit enqueue; result recorded in `monkey-test-engineer` agent-log (report optional per classification) |
| stress | 4 | `tests/stress/test_production_achievement_stress.py` (NEW, mirror `TestResourceHistoryAsyncStress`) — concurrent jobs on shared `heavy_query_slot`; `tests/stress/test_base_job_semaphore_stress.py` reused generically |
| soak | 4 | Reuse `tests/integration/test_soak_workload.py` harness; confirm PA traffic mix with `stress-soak-engineer` |

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | cdd-kit test select | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | cdd-kit test select | 1 | test-evidence.yml |
| changed-area | yes | cdd-kit test select | 1 | test-evidence.yml |
| contract | if affected | cdd-kit validate | 1 | test-evidence.yml |
| quality | if configured | ci-gates.md | 1 | test-evidence.yml |
| full | final/CI | cdd-kit test run --phase full | 1 | test-evidence.yml |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_production_achievement_routes.py::TestReportRoute | update | current tests assert synchronous forwarding kwargs; rewritten for 202/200-spool-hit/503 branches (AC-1, AC-2, AC-8) |
| tests/test_production_achievement_service.py | update | pin `build_achievement_rows()` as test-only golden (no longer called on request path) |
| tests/test_spool_routes.py | update | add `production_achievement` namespace cases alongside existing per-namespace parametrized tests |
| tests/test_query_cost_policy.py | update | add worker to `_APPROVED_CALLERS["base_chunked_duckdb_job"]` |
| tests/test_job_registry.py | update | add `TestAlwaysAsyncField` method only — do NOT bump the 12-count (worker-registered types excluded from `TestJobServiceRegistrations`, per eap-alarm/resource-history precedent) |
| tests/test_env_contract.py | update | add `test_production_achievement_async_env_vars_pinned_defaults` |
| tests/test_frontend_duckdb_parity.py, tests/fixtures/frontend_compute_parity.json | update | add PA achievement_rate scalar-formula case set alongside existing yield/reject/hold classes |
| tests/integration/test_production_achievement_filter_cache_reuse.py, test_production_achievement_mysql_roundtrip.py | none (reused) | targets/filter_cache untouched by this change |

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- PA-01..PA-05 shift-code/output-date/PA-05-predicate semantics — unchanged; already covered by `tests/test_production_achievement_shift_code.py`, `tests/test_production_achievement_output_date.py`, `tests/test_production_achievement_service.py::TestPA05PredicateSQL`; only re-verified via the AC-7 parity diff.
- Targets `PUT`/permission endpoints (`TestPutTargetsRoute`, `TestGetTargetsRoute`, admin permission tests) — behavior unchanged, no new tests.
- `sql/production_achievement.sql` PA-05 predicate rewrite — reused verbatim in chunk SQL (change-request non-goal).
- CSS/visual governed-token tests — no new CSS surface; async states reuse shared components.
- Real-Oracle nightly assertions inside `test_production_achievement_rq_async.py` beyond mock scaffolding — deferred to nightly `integration_real` gate, not Tier-1 pre-merge.

## Notes

- Env defaults: `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB=on` (no gradual flag, `always_async=True`), `PRODUCTION_ACHIEVEMENT_WORKER_QUEUE="production-achievement-query"`, `PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS=1800` — module-level constants, use `monkeypatch.setattr()` not `setenv`.
- `tests/integration/test_production_achievement_rq_async.py` MUST carry `pytestmark = pytest.mark.integration_real`; CI-blocking 202/200/503 coverage lives in `tests/test_production_achievement_routes.py` instead, mocking `is_async_available()` + enqueue fn only (CI has no Redis).
- Chunk-seam KEY fixture: one `(output_date, shift_code, SPECNAME)` group with `TRACKOUTTIMESTAMP` rows in both chunk-1 (pre-midnight) and chunk-2 (post-midnight) — assert exactly one row after `post_aggregate`.
- `_APPROVED_CALLERS`, job-registry `always_async` assertion, and `_ALLOWED_NAMESPACES` entry must land in the same PR as the worker/spool-write code.
