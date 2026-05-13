---
change-id: resource-history-perf
schema-version: "1.0"
date: 2026-05-13
reviewer: qa-reviewer
verdict: approved-with-risk
---

# QA Report — resource-history-perf

## AC Coverage Table

| AC-id | Covered by | Verdict |
|---|---|---|
| AC-1: 404/400 on missing or unknown query_id | `test_resource_history_routes.py::TestResourceHistoryProgressAPI::test_progress_missing_query_id_returns_400` (400 confirmed); `::test_progress_unknown_query_id_returns_404` (404 confirmed) | PASS |
| AC-2: Redis keys cover last ~3 months after startup; TTL ≥ 86 400 s | `test_resource_history_prewarm.py::TestResourceHistoryPrewarm::test_prewarm_generates_correct_date_chunks` verifies chunk count and date range; `test_prewarm_skips_cached_keys` verifies TTL path. No real-Redis TTL assertion at unit tier — deferred to nightly integration gate. | PARTIAL — nightly gate required |
| AC-3: historical end_date < today − 2 d → TTL 86 400 s; recent keeps short TTL | `test_resource_history_service.py::TestTtlBifurcation::test_historical_query_gets_long_ttl` (today−3); `::test_recent_query_keeps_short_ttl` (today); `::test_ttl_boundary_exactly_2_days_ago` (open boundary). Implementation in `_is_historical()` / `get_chunk_ttl()` is correct. | PASS |
| AC-4: startup survives Oracle unreachable | `test_resource_history_prewarm.py::TestResourceHistoryPrewarm::test_prewarm_survives_oracle_failure` confirms no raise + warning log; `::TestWarmupSchedulerJobFunction::test_warmup_resource_history_job_function_does_not_raise_on_oracle_error` confirms scheduler job boundary. `test_redis_chaos.py::test_resource_history_prewarm_redis_unavailable` is listed in test-plan but **does not exist** in the file — deferred to nightly. | PARTIAL — redis-chaos extension pending |
| AC-5: progress 200 returns 5 fields; status enum valid | `test_resource_history_routes.py::test_progress_running_query_returns_200_with_shape` (all 5 fields + running); `::test_progress_done_query_returns_200_status_done` (status mapping completed→done). Contract tests `test_api_contract.py::test_resource_history_progress_endpoint_in_inventory` and `::test_resource_history_progress_response_matches_data_shape_contract` are named in test-plan but **absent** from test_api_contract.py as of this review. | PARTIAL — contract test gap |
| AC-6: progress bar visible during batch; disappears on done | `App.vue` implements `startPolling` / `stopPolling` / `isPolling` + `progressPercent` reactive refs. `fetchProgress` sets `isPolling=false` on `done`. e2e browser tests (`test_resource_history_browser_e2e.py`) are listed in test-plan but not included in the 78/78 pytest run (pre-merge scope). | PARTIAL — e2e browser tests nightly |
| AC-7: polling stops after done or error | `App.vue::fetchProgress` calls `stopPolling()` on `status=done`, `status=error`, and on network exception — zombie polling prevented. Playwright extensions (`api-failure.spec.js`, `malformed-input.spec.js`) for 503 mid-poll and malformed response **not yet added** (grep finds no "progress" in those files). | PARTIAL — Playwright extensions pending |
| AC-8: pre-warm does not overwrite longer-TTL keys | `test_cache_integration.py::TestResourceHistoryPrewarmIdempotency::test_historical_ttl_does_not_overwrite_longer_ttl` verifies `skip_cached=True` is always passed and Oracle is not called when all chunks are cached. `test_resource_history_prewarm.py::test_prewarm_skips_cached_keys` corroborates. Real-Redis TTL assertion deferred to nightly. | PASS (mock tier) |

## Risks and Deferred Items

**RISK-1 (HIGH — blocks Playwright CI gate):** AC-7 Playwright extensions are missing. `api-failure.spec.js` and `malformed-input.spec.js` have no `progress polling` tests. The ci-gates.md lists `playwright-resilience` and `playwright-data-boundary` as **required pre-merge** gates. These will fail unless the extensions are added before merge.

**RISK-2 (MEDIUM):** AC-5 contract tests (`test_api_contract.py::test_resource_history_progress_endpoint_in_inventory`, `::test_resource_history_progress_response_matches_data_shape_contract`) appear in the test-plan but do not exist. The api-contract.md and data-shape-contract.md are correctly updated, but the programmatic enforcement is absent. The `test_route_matrix_complete` sweep count in `test_api_contract.py` baseline is `12` for `resource_history_routes.py` — not verified against new endpoint count.

**RISK-3 (LOW):** Test-plan names for AC-1 (`test_progress_missing_query_id`, `test_progress_unknown_query_id`) do not match actual method names (`test_progress_missing_query_id_returns_400`, `test_progress_unknown_query_id_returns_404`). Functionally equivalent; only traceability is affected.

**RISK-4 (LOW):** AC-4 redis-chaos extension (`tests/integration/test_redis_chaos.py::test_resource_history_prewarm_redis_unavailable`) listed in test-plan does not exist. Deferred to nightly; the oracle-unreachable path is covered at unit tier.

**RISK-5 (LOW):** `prewarm_last_n_months` uses `cache_prefix="resource_history_prewarm"` but the progress endpoint calls `get_batch_progress("resource_history", query_id)` — different prefixes. Pre-warm progress is therefore not visible via the progress endpoint. This is by design (pre-warm uses its own prefix; per-query progress uses the live query prefix), but should be confirmed as intentional in the proposal.

## Overall Verdict

**approved-with-risk**

Local gates (78/78 pytest, 302/302 Vitest, 0 type-check errors, 0 CSS errors, cdd-kit validate all pass) are green. Core backend implementation (TTL bifurcation, pre-warm, progress endpoint) is correctly implemented and unit-tested. The change is blocked from full pre-merge clearance by two gaps that must be resolved before the CI gates can turn green:

1. **RISK-1 (must fix before merge):** Add progress polling tests to `api-failure.spec.js` and `malformed-input.spec.js` to satisfy required Playwright CI gates.
2. **RISK-2 (should fix before merge):** Add two contract tests to `test_api_contract.py` for endpoint inventory and response shape; update the `resource_history_routes.py` baseline count from 12 to 13.
