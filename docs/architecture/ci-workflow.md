# CI Workflow & GunicornHarness Notes

Promoted learnings from project history — CI environment setup and GunicornHarness subprocess configuration.

## New Playwright Specs Require Browser Install in CI

**GitHub Actions runners have no pre-installed Chromium.** When a PR first introduces a Playwright spec for a page, add this step to `frontend-tests.yml` *before* the `npx playwright test …` step:

```yaml
- name: Install Playwright browsers
  run: npx playwright install --with-deps chromium
```

Without this, the runner exits with "Executable doesn't exist" and all tests fail with no output.

Note: The global `CLAUDE.md §Hard rules #2` ("do not run `playwright install`") applies only to the shared-browser host machine. It does NOT apply to CI runners.

Evidence: `downtime-analysis-page` — fixed in commit `6fac60c`.

## GunicornHarness — App URI and PYTHONPATH

**GunicornHarness subprocess must use `mes_dashboard:create_app()` (not `src.mes_dashboard.app:create_app()`) and prepend `src/` to `PYTHONPATH`.** Without both, the subprocess gets `ModuleNotFoundError: No module named 'mes_dashboard'`.

Use the same pattern as the existing `gunicorn_workers` fixture in `tests/integration/conftest.py`.

Pattern: `tests/integration/_multi_worker_harness.py::GunicornHarness.start()`

Evidence: `gunicorn-preload-workers`.

## GunicornHarness — Environment Isolation

**A `GunicornHarness` subprocess must pop `FLASK_ENV`, `FLASK_TESTING`, and `PYTEST_CURRENT_TEST`, and set `REDIS_ENABLED=true` before `Popen`.** Without this, prewarms never start.

Why: `is_testing_runtime` in `app.py:799` is `True` when any of `app.config["TESTING"]`, `app.testing`, or `os.getenv("PYTEST_CURRENT_TEST")` is set — all three are set by `tests/conftest.py`. This guard silently skips all single-run prewarms.

Pattern: `src/mes_dashboard/app.py:798-818`; `tests/integration/_multi_worker_harness.py:424-435`; `tests/conftest.py:18-19`

Evidence: `gunicorn-preload-workers`.

## GunicornHarness — Prewarm Sentinel to Assert

**Integration tests asserting exactly-one prewarm execution must check `"resource_history DuckDB prewarm background thread started"`, not `"prewarm complete"`.** `start_duckdb_prewarm()` logs "background thread started" on every call but logs "prewarm complete" only after a full Oracle load. If `_try_reuse_existing()` finds a valid `tmp/resource_history.duckdb`, the thread exits silently.

Asserting "prewarm complete" fails spuriously in warm-cache environments (e.g., a running production service has already written the file today).

Pattern: `tests/integration/test_preload_fork_safety.py:113-117, 368-378`

Evidence: `gunicorn-preload-workers`.

## GunicornHarness — Internal Metrics Env Vars

**GunicornHarness must set both `REGISTER_INTERNAL_METRICS=true` AND `INTERNAL_METRICS_ENABLED=1` to reach `/internal/metrics`.** `REGISTER_INTERNAL_METRICS` is env-var-overrideable via `_bool_env()` in `Config` (default `False`). Clearing `FLASK_ENV` (required to allow prewarms) removes the `TestingConfig.REGISTER_INTERNAL_METRICS=True` override — so both env vars must be set explicitly in the harness.

Pattern: `src/mes_dashboard/config/settings.py:53, 179`; `tests/integration/_multi_worker_harness.py:434-436`

Evidence: `gunicorn-preload-workers`.

## Playwright CI-Safe Specs — Use `page.goto()` Not `page.request.post()`

**`page.request.post()` (used by `loginViaApi` in `_auth.js`) is a direct Node.js HTTP call from the Playwright test runner — it cannot be intercepted by `page.route()` and throws `ECONNREFUSED` immediately when no Flask server is running.** For resilience-style specs that must pass vacuously in CI (no live server), use `page.goto(PAGE_URL, { waitUntil: 'networkidle', timeout: 30_000 }).catch(() => {})` and add an early-return guard instead of calling `loginViaApi`.

Pattern: `frontend/tests/playwright/downtime-analysis.spec.js` (reference — never calls `loginViaApi`); `frontend/tests/playwright/resource-history-async.spec.ts` (fixed in `f8b15d6`).

Evidence: `resource-history-rq-async` — CI run failed (all 3 tests ECONNREFUSED at `_auth.js:55`); fixed by removing `loginViaApi` and replacing with direct `page.goto`.

**New specs must front-load a FAST no-server pre-check before any `waitForFunction`.** Read `body` text with a short timeout (~5s) and bail immediately if it's near-empty (`< 50` chars) — never let every test burn the full `waitForFunction` timeout waiting for a theme root that will never mount. N tests × timeout × retries turns a no-dev-server CI run into a multi-minute stall. Pattern: `frontend/tests/playwright/resource-history-async.spec.ts` (`< 50`-char body check before the `networkidle` goto returns).

Evidence: `production-achievement-async-spool` — `production-achievement-async.spec.ts`'s `gotoAndWaitForApp` initially skipped this pre-check (went straight to a 20s `waitForFunction` per test) → ~25 min CI slow-fail; mirroring the fast check (commit `a83e7331`) dropped it to 5.8s.

Second occurrence, `production-achievement-overhaul`: 5 rewritten spec files shipped without this gate (a bare `waitForFunction(20s/30s)` right after `goto`), producing a ~50-65s/test tax and blowing the step timeout. Shortening the `waitForFunction` timeout value alone (first fix attempt, commit `36972fbc`) did not help — `waitForFunction` does not reliably honor its own `timeout` on a frame whose navigation just failed, confirmed by direct comparison against `production-achievement-async.spec.ts`/`production-achievement-monkey.spec.ts`'s `gotoAndWaitForApp()`, which already gated correctly and ran in ~200-300ms/test. Real fix (the check must gate, i.e. `return` before ever calling `waitForFunction`, not just bound its timeout): commit `76c584a3`.

## Playwright `pageRendered` Guard — Use App-Specific Content, Not `bodyText.length`

**Chrome's ECONNREFUSED error page body can exceed 100 chars.** A guard like `pageRendered = bodyText.length > 100` will incorrectly report the Vue app as mounted on the browser error page, causing assertions to run against error-page DOM and fail unexpectedly. Use app-specific content detection instead: `bodyText.includes('<feature-keyword>') || (await page.locator('.theme-<name>, #<app-id>').count()) > 0`.

Pattern: `frontend/tests/playwright/resource-history-async.spec.ts` — AC-9 `pageRendered` check uses `bodyText.includes('設備') || bodyText.includes('KPI') || locator('.theme-resource-history, #resource-history-app').count() > 0`.

Evidence: `resource-history-rq-async` — fix commit `f8b15d6`.

## Playwright `page.route()` Ordering Is LIFO

**Playwright matches the most-recently-registered `page.route()` handler first.** Register catch-all/base mocks (auth, generic API fallback) FIRST so they have the lowest match priority, then register specific per-test route overrides LAST so they win. Registering in the opposite order causes the catch-all to shadow the specific mock and the test asserts against the wrong (fallback) response.

Pattern: `frontend/tests/playwright/db-scheduling.spec.ts` — catch-all + base routes registered first, specific queue route registered last with an explicit `// LIFO: higher priority` comment.

## Async-Gated Route Unit Tests — Mock `is_async_available()`, Not Spool-Hit

**The `backend-tests` CI job has no Redis service.** `is_async_available()` returns `False` when Redis is unreachable, causing routes for async-only domains (production-history, reject-history) to fall through to a 503 degraded response. Tests that expected 200/202 fail with 503.

**Wrong approach — spool-hit mock:**
```python
# Fragile in CI: spool directory is empty; mock path resolution may mismatch
patch("...get_spool_file_path", return_value="/tmp/fake.parquet")
patch("...query_production_history", return_value={...})
```

**Correct approach — async-path mock:**
```python
@patch(
    "mes_dashboard.services.production_history_job_service.enqueue_production_history_query",
    return_value=("job-id-test-123", None),
)
@patch(
    "mes_dashboard.services.async_query_job_service.is_async_available",
    return_value=True,
)
def test_something(self, mock_async, mock_enqueue):
    response = self.client.post("/api/production-history/query", json={...})
    self.assertIn(response.status_code, (200, 202))
```

This ensures the route walks the legacy async path (202) and never reaches the degraded 503 branch, regardless of Redis availability.

The same applies to any route that has `if is_async_available():` as its only non-spool dispatch branch.

Pattern: `tests/test_api_contract.py::TestProductionHistoryQueryModeContract::test_query_payload_dates_optional_with_identifier_tokens`

Evidence: `production-reject-history-migration` — CI failures on `a96acd5` fixed in same commit.
