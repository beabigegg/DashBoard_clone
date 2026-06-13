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
