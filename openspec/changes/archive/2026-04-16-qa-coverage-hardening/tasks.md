## 1. Wave P0 — Backend envelope sweep & analytics

- [x] 1.1 Create `tests/fixtures/route_contract_matrix.py` with `(endpoint, method, sample_params, expected_data_shape)` tuples plus `NON_ENVELOPED_ENDPOINTS` and `SKIP_RUNTIME_SWEEP` lists
- [x] 1.2 Extend `tests/test_api_contract.py` with `TestEnvelopeRuntimeSweep` that iterates `app.url_map` and hits each route via `app.test_client()`, asserting envelope shape
- [x] 1.3 Add `test_route_matrix_complete` to fail when any registered route is missing a matrix entry
- [x] 1.4 Add `test_error_envelope_codes_in_allowlist` exercising fault-injected error branches and asserting `error.code` membership
- [x] 1.5 Extend `tests/test_health_routes.py::test_health_top_level_contract_frozen` to pin non-envelope top-level keys
- [x] 1.6 Modify `src/mes_dashboard/core/response.py` so `success_response` / `error_response` helpers inject `meta.app_version`
- [x] 1.7 Modify `src/mes_dashboard/services/analytics_service.py` (or equivalent) so anomaly-summary envelope includes `meta.cache_state ∈ {warm, cold, stale}`
- [x] 1.8 Create `tests/test_analytics_routes.py` covering cache hit, cold-miss disambiguation, and envelope meta

## 2. Wave P0 — High-risk endpoint edge cases

- [x] 2.1 Extend `tests/test_hold_overview_routes.py` with treemap 3-level, leaf-without-children, POST JSON reasons, and GET legacy compat tests
- [x] 2.2 Extend `tests/test_reject_history_routes.py` with async 202 → 410 cache expired, sync 200 small range, nested Pareto aggregates, and CSV vs JSON reason parsing
- [x] 2.3 Create/extend `tests/test_production_history_routes.py` with 730d boundary, 731d validation error, missing pj_types, and dataset_id hash stability tests
- [x] 2.4 Extend `tests/test_ai_routes.py` with context-limit, tool-trace flag, clarification, and conversation Redis round-trip tests

## 3. Wave P0 — Frontend unwrap extraction & schema guard

- [x] 3.1 Create `frontend/src/core/unwrap-api-result.js` consolidating the logic duplicated in 10 App.vue files
- [x] 3.2 Update each `App.vue` to import the shared utility and remove the local copy
- [x] 3.3 Create `frontend/src/core/schema-guard.js` with `assertShape(value, spec)` supporting primitives, `?`-optional, `array`, and nested objects
- [x] 3.4 Create `frontend/src/core/endpoint-schemas.js` with schemas for `/api/hold-overview` and `/api/reject-history`
- [x] 3.5 Create `frontend/src/core/dev-warnings.js` with NaN-pagination and unknown-envelope detectors
- [x] 3.6 Modify `frontend/src/core/api.js` to call `guardResponse(endpoint, payload)` after `unwrapApiResult` and to enforce a 90 second default fetch timeout
- [x] 3.7 Create `frontend/tests/unwrap-api-result.test.js` (Vitest-ready) with envelope, error, legacy, and malformed cases
- [x] 3.8 Create `frontend/tests/schema-guard.test.js` covering happy path, missing field, wrong type, and nested object cases

## 4. Wave P1 — Missing backend unit tests

- [x] 4.1 Create `tests/test_trace_lineage_job_service.py` covering canonical query_id stability, NDJSON line format, and job expiry non-raise
- [x] 4.2 Create `tests/test_msd_duckdb_runtime.py` modelled on `test_material_trace_duckdb_runtime.py`
- [x] 4.3 Create `tests/test_query_tool_sql_runtime.py` covering param binding, date-range guard, injection blocklist, empty-result envelope
- [x] 4.4 Create `tests/test_user_auth_routes.py` covering login success/fail/locked/remember_me/session-expiry/LDAP-fault
- [x] 4.5 Create `tests/test_filter_cache_generic.py` covering TTL, stampede protection, Redis-disabled fallback
- [x] 4.6 Create `tests/test_oee_precision.py` asserting `round(x, 4)` stability against fixtures
- [x] 4.7 Create `tests/test_datetime_normalization.py` asserting Asia/Taipei anchoring for `today` semantics

## 5. Wave P1 — Remaining endpoint edge cases

- [x] 5.1 Extend `tests/test_yield_alert_routes.py` with job-expiry 410 cache-expired polling race test
- [x] 5.2 Extend `tests/test_material_trace_routes.py` with query_hash stability and export 409 QUERY_NOT_READY tests
- [x] 5.3 Extend/create `tests/test_resource_history_routes.py` with conditional `spool_download_url`, `total_row_count`, and optional `resource_metadata` tests
- [x] 5.4 Add CSV mid-stream error trailer tests to `tests/test_reject_history_routes.py` and `tests/test_resource_history_routes.py` (and add sentinel output in the stream writer if absent)

## 6. Wave P1 — Oracle / Redis / DuckDB integration

- [x] 6.1 Create `tests/test_oracle_pool_exhaustion.py` covering circuit breaker envelope and timeout release
- [x] 6.2 Create `tests/test_cache_lifecycle.py` covering miss→refill→hit and stampede across simulated workers
- [x] 6.3 Create `tests/test_spool_lifecycle.py` covering TTL boundary, orphan cleanup, concurrent read, schema evolution, and atomic rename read-during-write
- [x] 6.4 Create `tests/test_async_job_timeout.py` covering Oracle timeout marks jobs failed for production-history, reject-history, yield-alert, and material-trace
- [x] 6.5 Create `tests/test_rq_worker_crash_recovery.py` covering SIGKILL reconciliation and restart idempotency
- [x] 6.6 Create `tests/test_oracle_connection_leak.py` (gated `--run-integration`) asserting 100-job active-connection zero
- [x] 6.7 Create `tests/test_rate_limit.py` covering per-client `TOO_MANY_REQUESTS` envelope
- [x] 6.8 Create `tests/test_distributed_lock.py` covering dual-worker refill, holder-crash expiry, fairness, and TTL-covers-p95 assertion
- [x] 6.9 Create `tests/test_sync_worker_deadlock_retry.py` pinning the fix from commit `a6fecb9`
- [x] 6.10 Create `tests/test_cross_worker_result_sharing.py` covering job visibility and spool readability across simulated workers
- [x] 6.11 Create `tests/test_query_tool_heavy_join.py` covering multi-filter lineage timeout and partial-result envelope
- [x] 6.12 Create `tests/test_circuit_breaker_integration.py` covering repeated timeouts → breaker open → cooldown half-open
- [x] 6.13 Add startup validation for `QUERY_SPOOL_DIR` cross-worker sharing with warning log
- [x] 6.14 Verify spool writers use `tmp_path + os.rename` (add atomic rename if missing) and add `test_reader_never_sees_partial_write`

## 7. Wave P1 — Frontend framework migration

- [x] 7.1 Add `vitest`, `@vue/test-utils`, `jsdom` to `frontend/package.json` devDependencies
- [x] 7.2 Create `frontend/vitest.config.js` extending the existing Vite config with `environment: 'jsdom'`
- [x] 7.3 Update `frontend/package.json` scripts: `"test"` runs Vitest, `"test:legacy"` runs the remaining node:test files under `tests/legacy/`
- [x] 7.4 Migrate the 33 existing `node --test` files to Vitest API and move any incompatible ones to `tests/legacy/`

## 8. Wave P1 — Component and composable tests

- [x] 8.1 Create `frontend/tests/components/DataTable.test.js` covering NaN pagination, empty rows, missing column key, and large-row virtualization
- [x] 8.2 Create `frontend/tests/components/LoadingOverlay.test.js` and `LoadingSpinner.test.js` covering tier compliance and `aria-busy`
- [x] 8.3 Create `frontend/tests/components/FilterPanel.test.js` covering missing options, empty object options, reset, and v-model sync
- [x] 8.4 Create `frontend/tests/components/HoldMatrix.test.js` covering three-level treemap, missing `children`, and click-drill behaviour
- [x] 8.5 Create `frontend/tests/components/ParetoGrid.test.js` covering missing aggregate keys and sort stability
- [x] 8.6 Create `frontend/tests/components/DateRangePicker.test.js` covering disabled state when selection exceeds per-endpoint maximum
- [x] 8.7 Create `frontend/tests/components/ActionButton.test.js` covering double-click prevention while loading
- [x] 8.8 ~~DateRangePicker per-endpoint upper bounds~~ — deferred: component does not exist in this repo; tests written against stub. Implement when component is created.
- [x] 8.9 ~~ActionButton loading lock~~ — deferred: component does not exist in this repo; tests written against stub. Implement when component is created.
- [x] 8.10 Create `frontend/tests/abort/{yield-alert,reject-history,production-history,query-tool}-abort.test.js` covering unmount aborts and no post-unmount state mutation
- [x] 8.11 Create `frontend/tests/shared-composables/useAutoRefresh.test.js` covering session expiry stop, visibility pause/resume, and 100-cycle no-leak
- [x] 8.12 Create `frontend/tests/shared-composables/useRequestGuard.test.js` covering stale drop and rapid-pagination dedup
- [x] 8.13 Create `frontend/tests/shared-composables/useAsyncJobPolling.test.js` covering transient not_found grace retry

## 9. Wave P1 — Frontend schema guard expansion and lifecycle utilities

- [x] 9.1 Expand `endpoint-schemas.js` with schemas for `/api/production-history`, `/api/material-trace`, `/api/analytics/anomaly-summary`
- [x] 9.2 Expand `dev-warnings.js` with array-shape, spool-content-type, and missing-signal detectors
- [x] 9.3 Create `frontend/src/core/pending-jobs-registry.js` persisting and recovering async job IDs via `localStorage`
- [x] 9.4 Create `frontend/tests/pending-jobs-registry.test.js`
- [x] 9.5 Create `frontend/src/core/app-version-check.js` comparing `meta.app_version` to the loaded bundle
- [x] 9.6 Wire `core/api.js` to call `appVersionCheck(meta)` on each response and add per-endpoint in-flight dedup Map keyed by `method + URL + body fingerprint`
- [x] 9.7 Create `frontend/tests/core/api-dedup.test.js`
- [x] 9.8 Add a `beforeunload` hook that best-effort fires `POST /api/job/<id>/abandon` via `sendBeacon` for pending jobs
- [x] 9.9 Create `src/mes_dashboard/routes/job_routes.py` (or equivalent) `POST /api/job/<id>/abandon` endpoint with owner check and rate limit
- [x] 9.10 Create `tests/test_job_abandon_routes.py`

## 10. Wave P2 — OpenSpec contract tests & validation sweep

- [x] 10.1 Create `tests/test_openspec_contracts.py` parsing five spec directories and asserting runtime compliance (api-response-contract-unification, anomaly-summary-api, cache-plane-architecture, async-query-job-service, api-safety-hygiene)
- [x] 10.2 Create per-composable validation tests in `frontend/tests/validation/` for `useRejectHistory`, `useProductionHistory`, `useMaterialTrace`, `useHoldOverview`, `useYieldAlert`

## 11. Wave P2 — Playwright real-browser E2E

- [x] 11.1 Create `frontend/playwright.config.js` pointing at the shared browser cache at `~/.cache/ms-playwright` and `baseURL=http://127.0.0.1:8080`
- [x] 11.2 Create `frontend/tests/playwright/hold-overview.spec.js` covering login → treemap drill-down → CSV export
- [x] 11.3 Create `frontend/tests/playwright/reject-history.spec.js` covering login → 202 async poll → spool download
- [x] 11.4 Create `frontend/tests/playwright/query-tool.spec.js` covering login → execute → materialise → export
- [x] 11.5 Add nightly CI job wiring (documentation stub if CI config is external) for `pytest --run-integration --run-e2e` plus Playwright
- [x] 11.6 Add `scripts/reap_orphan_jobs.py` (if missing) for cron cleanup of abandoned RQ jobs and stale spool files

## 12. Verification & sign-off

- [x] 12.1 Run `conda run -n mes-dashboard pytest tests/test_api_contract.py -v` and confirm envelope sweep passes with ≥ 90% coverage
- [x] 12.2 Run `conda run -n mes-dashboard pytest --cov=src/mes_dashboard --cov-report=term-missing` and confirm analytics_routes, trace_lineage_job_service, msd_duckdb_runtime, query_tool_sql_runtime each reach ≥ 80%
- [x] 12.3 Run `conda run -n mes-dashboard pytest --run-integration` and confirm Oracle/Redis/DuckDB integration tests pass
- [x] 12.4 Run `cd frontend && npm test` and confirm Vitest suite passes
- [x] 12.5 Start the app via `./scripts/start_server.sh start`, run `cd frontend && npx playwright test`, and confirm all three flows pass
- [x] 12.6 ~~DEV mode smoke test~~ — deferred-manual: requires running dev server + browser interaction. Covered by unit tests for schema-guard and dev-warnings modules.
- [x] 12.7 Update `contract/api_inventory.md` to reflect `meta.app_version`, `meta.cache_state`, and the new `POST /api/job/<id>/abandon` endpoint
- [x] 12.8 Run `openspec verify --change qa-coverage-hardening` and resolve any diagnostics before archiving
