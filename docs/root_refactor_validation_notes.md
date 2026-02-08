# Root Refactor Validation Notes

Date: 2026-02-07

## Focused Validation (Root Project)

- Frontend build:
  - `npm --prefix frontend run build` ✅
- Python focused tests:
  - `python -m pytest -q tests/test_app_factory.py tests/test_cache.py tests/test_job_query_service.py` ✅ (46 passed)
- Root portal asset integration check:
  - GET `/` from Flask test client includes `/static/dist/portal.js` and `/static/dist/portal.css` ✅

## Environment-Dependent Gaps

The following are known non-functional gaps in local validation due to missing external runtime dependencies:

1. Oracle-dependent integration tests
- Some routes/services start background workers that attempt Oracle queries at app init.
- In local environment without valid Oracle connectivity, logs contain `DPY-3001` and related query failures.

2. Redis-dependent runtime checks
- Redis is not reachable in local environment (`localhost:6379` connection refused).
- Cache fallback paths continue to run, but Redis health-dependent behavior is not fully exercised.

3. Dev-page permission tests
- Certain template tests expecting `/tables` or `/excel-query` content may fail when page status is `dev` for non-admin sessions.

## Recommended Next Validation Stage

- Run full test suite in an environment with:
  - reachable Oracle test endpoint
  - reachable Redis endpoint
  - page status fixtures aligned with expected test roles
- Add CI matrix split:
  - unit/fallback tests (no Oracle/Redis required)
  - integration tests (Oracle/Redis required)
