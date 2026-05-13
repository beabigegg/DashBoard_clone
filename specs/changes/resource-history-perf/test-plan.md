---
change-id: resource-history-perf
schema-version: "1.1"
last-changed: 2026-05-13
risk: medium
tier: 3
---

# Test Plan: resource-history-perf

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file / command | tier |
|---|---|---|---|
| AC-1: 404 unknown / 400 missing query_id | unit-route | `tests/test_resource_history_routes.py::TestResourceHistoryProgressAPI::test_progress_missing_query_id` | 1 |
| AC-1 | unit-route | `tests/test_resource_history_routes.py::TestResourceHistoryProgressAPI::test_progress_unknown_query_id` | 1 |
| AC-2: Redis keys cover last ~3 months after startup; TTL ≥ 86 400 s | integration | `tests/test_resource_history_prewarm.py::test_prewarm_seeds_three_months_of_chunks` | 2 |
| AC-2 | integration | `tests/test_resource_history_prewarm.py::test_prewarm_redis_ttl_ge_86400` | 2 |
| AC-3: historical end_date < today − 2 d → TTL = 86 400 s; recent keeps short TTL | unit-service | `tests/test_resource_history_service.py::TestTtlBifurcation::test_historical_chunk_gets_long_ttl` | 1 |
| AC-3 | unit-service | `tests/test_resource_history_service.py::TestTtlBifurcation::test_recent_chunk_keeps_short_ttl` | 1 |
| AC-4: startup survives Oracle unreachable | integration | `tests/test_resource_history_prewarm.py::test_prewarm_oracle_unreachable_logs_warning_no_exception` | 2 |
| AC-4 | resilience | `tests/integration/test_redis_chaos.py::test_resource_history_prewarm_redis_unavailable` | 2 |
| AC-5: progress 200 returns all 5 fields; status enum valid | unit-route | `tests/test_resource_history_routes.py::TestResourceHistoryProgressAPI::test_progress_running_response_shape` | 1 |
| AC-5 | unit-route | `tests/test_resource_history_routes.py::TestResourceHistoryProgressAPI::test_progress_done_response_shape` | 1 |
| AC-5 | contract | `tests/test_api_contract.py::test_resource_history_progress_endpoint_in_inventory` | 1 |
| AC-5 | contract | `tests/test_api_contract.py::test_resource_history_progress_response_matches_data_shape_contract` | 1 |
| AC-6: progress bar visible during batch; disappears on done | e2e-browser | `tests/e2e/test_resource_history_browser_e2e.py::test_progress_bar_shown_during_batch_query` | 3 |
| AC-6 | e2e-browser | `tests/e2e/test_resource_history_browser_e2e.py::test_progress_bar_disappears_on_status_done` | 3 |
| AC-7: polling stops after done / error | data-boundary | `frontend/tests/playwright/data-boundary/malformed-input.spec.js` (extend: `progress polling stops on done`) | 1 |
| AC-7 | resilience | `frontend/tests/playwright/resilience/api-failure.spec.js` (extend: `progress polling stops on error`) | 2 |
| AC-8: pre-warm does not overwrite longer-TTL keys | integration | `tests/test_cache_integration.py::TestResourceHistoryPrewarmIdempotency::test_prewarm_skip_cached_preserves_longer_ttl` | 2 |
| AC-8 | integration | `tests/test_resource_history_prewarm.py::test_prewarm_idempotent_on_restart` | 2 |

## Test Families Required

| family | files | tier | run gate |
|---|---|---|---|
| unit-service | `tests/test_resource_history_service.py` (extend) | 1 | pre-merge |
| unit-route | `tests/test_resource_history_routes.py` (extend) | 1 | pre-merge |
| contract | `tests/test_api_contract.py` (extend) | 1 | pre-merge |
| data-boundary | `frontend/tests/playwright/data-boundary/malformed-input.spec.js` (extend) | 1 | pre-merge |
| integration | `tests/test_resource_history_prewarm.py` (new) | 2 | pre-merge |
| integration | `tests/test_cache_integration.py` (extend) | 2 | pre-merge |
| resilience | `frontend/tests/playwright/resilience/api-failure.spec.js` (extend) | 2 | pre-merge |
| resilience | `tests/integration/test_redis_chaos.py` (extend) | 2 | pre-merge |
| e2e-backend | `tests/e2e/test_resource_history_e2e.py` (extend) | 3 | pre-merge |
| e2e-browser | `tests/e2e/test_resource_history_browser_e2e.py` (extend) | 3 | pre-merge |
| stress | `tests/stress/test_resource_history_stress.py` (extend: concurrent progress polls N=50) | 3 | nightly |

## Out of Scope

- Visual snapshot tests (progress bar styling is not a new design system component).
- Soak tests — additive change; Redis memory budget verified in proposal (≤1.4 MB).
- Frontend OEE formula parity tests — unaffected by this change.
- `RESOURCE_HISTORY_PREWARM_MONTHS > 3` configuration paths — not the default.

## Notes

- `tests/test_resource_history_prewarm.py` is the only new file; all other families extend existing files.
- AC-4 (Oracle unreachable) must mock `oracledb` at the service boundary to remain tier-2 (mock-integration).
- AC-8 idempotency test in `test_cache_integration.py`: seed a Redis key with TTL=172 800 s, call `prewarm_last_n_months(skip_cached=True)`, assert TTL is unchanged.
- Stress extension (`N=50` concurrent progress polls) is nightly per project test-layer governance — not a pre-merge gate.
- `tests/integration/test_redis_chaos.py` already has Redis-unavailability fixtures; extend rather than duplicate.
