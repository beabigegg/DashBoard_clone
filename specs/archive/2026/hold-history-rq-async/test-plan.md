---
change-id: hold-history-rq-async
schema-version: 0.1.0
last-changed: 2026-06-13
risk: medium
tier: 2
---

# Test Plan: hold-history-rq-async

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_long_range_returns_202` | 0 |
| AC-1 | contract | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_202_response_has_job_id` | 0 |
| AC-2 | unit | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_short_range_returns_200_sync` | 0 |
| AC-2 | unit | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_async_flag_false_returns_200_sync` | 0 |
| AC-3 | integration | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncParity::test_worker_fn_parity_vs_sync` | 1 |
| AC-3 | unit | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_passes_params` | 0 |
| AC-4 | integration | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncParity::test_per_chunk_pct_milestones_fire_in_order` | 1 |
| AC-4 | integration | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncParity::test_pct_envelope_never_decreases` | 1 |
| AC-5 | e2e | `frontend/tests/playwright/hold-history-flat-table.spec.js` | 2 |
| AC-5 | e2e | `tests/e2e/test_hold_history_e2e.py::TestHoldHistoryQuery::test_long_range_returns_202_and_job_id` | 2 |
| AC-6 | contract | `tests/test_hold_history_routes.py::TestHoldHistoryConfigRoute::test_config_has_hold_async_keys` | 0 |
| AC-6 | unit | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_hold_async_enabled_default_is_true` | 0 |
| AC-6 | unit | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_hold_async_day_threshold_default_is_90` | 0 |
| AC-6 | unit | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncDispatch::test_hold_worker_queue_default_is_hold_history_query` | 1 |
| AC-6 | unit | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncDispatch::test_hold_job_timeout_default_is_1800` | 1 |
| AC-7 | integration | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncDispatch::test_enqueue_to_hold_history_queue` | 1 |
| AC-7 | integration | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncDispatch::test_enqueue_payload_contains_owner_and_params` | 1 |
| AC-8 | resilience | `tests/integration/test_hold_history_rq_async.py::TestHoldHistoryAsyncParity::test_worker_fn_failure_does_not_call_complete_job` | 1 |
| AC-8 | resilience | `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_redis_down_falls_back_to_sync` | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Route 202/200 branch; env-var defaults pinned via `monkeypatch.setattr()`; per-kwarg forwarding assertions |
| contract | 0 | API 202 shape; 4 HOLD_* env-var exact default values; `cdd-kit validate` passes |
| integration | 1 | `tests/integration/test_hold_history_rq_async.py` mirrors downtime 3-A pattern; `pytestmark = pytest.mark.integration_real`; row-count parity + per-chunk milestone ordering |
| e2e | 2 | Playwright long-range → `AsyncQueryProgress` renders then correct result; short-range → 200 sync unchanged |
| data-boundary | 1 | Async result envelope identical to sync payload; empty/malformed query handled |
| resilience | 1 | Redis-down degrades safely to sync; worker exception does not corrupt sync path |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_hold_history_routes.py::TestHoldHistoryQueryRoute::test_query_success` | extend | assert sync path still returns 200 when `HOLD_ASYNC_ENABLED=False` or range < threshold |
| `tests/e2e/test_hold_history_e2e.py::TestHoldHistoryQuery::test_query_returns_query_id` | extend | add assertion: short-range still returns sync query_id in 200 response |

## Out of Scope

- `execute_primary_query()` internals in `hold_dataset_cache.py` — worker wraps unmodified (AC-3 asserts parity, not internals).
- DA-11 two-parquet atomicity — hold-history uses a single spool.
- ADR-0003 date-range chunking exclusion — hold-history uses row-count chunking; ADR does not apply.
- `AsyncQueryProgress.vue` visual tests — covered by existing `frontend/tests/components/AsyncQueryProgress.test.js`; extend only if rendering context differs.
- Stress / soak — reuse `tests/stress/test_async_job_stress.py` and existing weekly soak; not pre-merge per test-layer governance.
- `today-snapshot` route — unaffected.

## Notes

- Env-var defaults must be asserted with exact values: `HOLD_ASYNC_ENABLED=True`, `HOLD_ASYNC_DAY_THRESHOLD=90`, `HOLD_WORKER_QUEUE="hold-history-query"`, `HOLD_JOB_TIMEOUT_SECONDS=1800`.
- Use `monkeypatch.setattr('mes_dashboard.services.hold_query_job_service.HOLD_ASYNC_ENABLED', ...)` — module-level constants are frozen at import; `os.environ` patching has no effect.
- Route per-kwarg assertions: use `call_args.kwargs[key]` style, not `assert_called_once_with()` whitelist.
- Per-chunk milestone test: assert sequence is non-decreasing, first milestone ≤ 5, last milestone == 100.
- `tests/integration/` pytestmark must be `pytest.mark.integration_real` — verify before adding mock tests there.
