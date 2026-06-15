---
change-id: resource-history-rq-async
schema-version: 0.1.0
last-changed: 2026-06-15
risk: high
tier: 1
---

# Test Plan: resource-history-rq-async

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 | unit | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_query_long_span_returns_202` | 0 |
| AC-1 | contract | `tests/test_api_contract.py::TestResourceHistoryAsyncContract::test_202_response_shape_has_job_id_and_status_url` | 0 |
| AC-2 | unit | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_query_short_span_returns_200_sync` | 0 |
| AC-2 | unit | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_query_async_flag_false_returns_200_sync` | 0 |
| AC-3 | integration | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_worker_fn_parity_vs_sync` | 1 |
| AC-3 | integration | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_coarse_milestones_fire_in_order` | 1 |
| AC-3 | integration | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_pct_envelope_never_decreases` | 1 |
| AC-4 | e2e | `frontend/tests/playwright/resource-history-async.spec.ts` | 2 |
| AC-5 | unit | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_resource_async_enabled_default_is_true` | 0 |
| AC-5 | unit | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_resource_async_day_threshold_default_is_90` | 0 |
| AC-5 | contract | `tests/test_env_contract.py::test_resource_async_env_vars_pinned_defaults` | 0 |
| AC-5 | integration | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncDispatch::test_resource_worker_queue_default_is_resource_history_query` | 1 |
| AC-5 | integration | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncDispatch::test_resource_job_timeout_default_is_1800` | 1 |
| AC-6 | unit | `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_redis_unavailable_falls_back_to_sync` | 0 |
| AC-6 | resilience | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_worker_exception_calls_complete_job_with_error` | 1 |
| AC-7 | unit | `tests/unit/test_resource_query_job_service.py::TestResourceQueryJobService::test_should_use_async_above_threshold` | 0 |
| AC-7 | unit | `tests/unit/test_resource_query_job_service.py::TestResourceQueryJobService::test_should_use_async_below_threshold_is_false` | 0 |
| AC-7 | integration | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncDispatch::test_enqueue_to_resource_history_queue` | 1 |
| AC-7 | integration | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncDispatch::test_enqueue_payload_owner_inside_params_dict` | 1 |
| AC-8 | unit | `tests/test_spool_routes.py::test_resource_dataset_stays_in_allowed_namespaces` | 0 |
| AC-9 | resilience | `tests/integration/test_resource_history_rq_async.py::TestResourceHistoryAsyncParity::test_job_timeout_produces_terminal_error_status` | 1 |
| AC-9 | unit | `tests/unit/test_resource_query_job_service.py::TestResourceQueryJobService::test_worker_fn_failure_reraises_and_sets_error` | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Route 202/200 branch; `should_use_async` threshold boundary; env-var defaults via `monkeypatch.setattr()`; `resource_dataset` allowlist regression |
| contract | 0 | API 202 shape; 4 `RESOURCE_*` env-var exact default values; `cdd-kit validate` passes |
| integration | 1 | `tests/integration/test_resource_history_rq_async.py`; `pytestmark = pytest.mark.integration_real`; enqueue→poll→view round-trip; `owner` inside `_params` dict; coarse milestone ordering |
| e2e | 2 | Playwright long-span → `AsyncQueryProgress` renders then results via `refreshView()`; short-span → sync 200 unchanged |
| resilience | 1 | Redis-down degrades to sync; worker exception calls `complete_job(error=...)` and re-raises; timeout yields terminal status |
| stress | 3 | Extend `tests/stress/test_resource_history_stress.py` for concurrent async-job load; nightly lane only |
| soak | 4 | Long-running worker stability; weekly lane; never pre-merge |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| `tests/test_resource_history_routes.py::TestResourceHistoryQueryRoute::test_successful_query` | extend | assert sync path still returns 200 when `RESOURCE_ASYNC_ENABLED=False` or span < threshold |
| `tests/test_env_contract.py` | extend | add `test_resource_async_env_vars_pinned_defaults` for 4 new `RESOURCE_*` vars with exact defaults |
| `tests/test_api_contract.py` | extend | add `TestResourceHistoryAsyncContract` class for 202 response shape assertion |
| `tests/test_spool_routes.py` | extend | add `test_resource_dataset_stays_in_allowed_namespaces` — regression guard, no new entry expected |
| `tests/stress/test_resource_history_stress.py` | extend | add concurrent async-job load scenario (nightly lane) |

## Out of Scope

- `execute_primary_query()` internals in `resource_dataset_cache.py` — worker wraps it unmodified; parity is structural.
- ADR-0003 re-classification — design.md documents it does not apply; no ADR change needed.
- `data-shape-contract.md` changes — spool schema is identical to sync path (design.md Key Decision 2).
- `AsyncQueryProgress.vue` visual tests — covered by existing component tests.
- New `_ALLOWED_NAMESPACES` entry — `resource_dataset` is already present; test is a regression guard only.
- `apply_view` OEE aggregation correctness — unchanged; covered by existing `test_resource_dataset_cache.py`.

## Notes

- Env defaults must be asserted with exact values: `RESOURCE_ASYNC_ENABLED=True`, `RESOURCE_ASYNC_DAY_THRESHOLD=90`, `RESOURCE_WORKER_QUEUE="resource-history-query"`, `RESOURCE_JOB_TIMEOUT_SECONDS=1800`.
- Use `monkeypatch.setattr('mes_dashboard.services.resource_query_job_service.RESOURCE_ASYNC_ENABLED', ...)` — module-level constants are frozen at import; `os.environ` patching has no effect.
- AC-7 regression guard: assert `call_args.kwargs["params"]["owner"]` is set inside `_params`, not only the separate `enqueue_job_dynamic(owner=...)` kwarg.
- Integration `pytestmark = pytest.mark.integration_real` must be present — verify before adding any mock-only test to `tests/integration/`.
- Milestone test: assert sequence is non-decreasing, first milestone ≤ 5, last milestone == 100.
