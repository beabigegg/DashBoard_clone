## Context

The MES Dashboard currently has 155 backend test files, 23 frontend test files, 18 e2e tests, and 5 stress tests. The backend has 57 services and 23 route modules; the frontend has 20 SPA applications. While core features (hold, reject, yield-alert, resource, query-tool, WIP) are well-covered, newer and auxiliary features have inconsistent or missing test coverage. There are two GitHub Actions workflows, but they only cover a subset of tests on specific path triggers.

The existing test infrastructure uses:
- **Backend**: pytest with markers `integration`, `e2e`, `stress`, `load`; conftest fixtures for Flask test client, circuit breaker reset, and modernization cache isolation.
- **E2E**: pytest-playwright with browser context fixtures (1280x720, zh-TW locale).
- **Stress**: Custom `StressTestResult` dataclass with concurrency/throughput metrics.
- **Frontend**: Node.js built-in test runner (`node --test`).

## Goals / Non-Goals

**Goals:**
- Produce a coverage matrix identifying every untested service, route, and frontend app
- Fill gaps so that every backend service has at least one unit test file
- Fill gaps so that every route module has integration tests exercising success and error paths
- Add e2e tests for all user-facing pages that currently lack them
- Add stress tests for high-traffic endpoints not yet covered
- Add frontend tests for SPA modules without any test files
- Extend CI workflows to run the complete test suite on relevant triggers

**Non-Goals:**
- Achieving a specific coverage percentage target (e.g., 80%) — focus is on breadth of feature coverage, not line-by-line metrics
- Rewriting or refactoring existing tests that already pass
- Adding visual regression testing or screenshot comparisons
- Performance benchmarking beyond stress test pass/fail thresholds
- Testing third-party library internals (Oracle driver, Redis client, DuckDB engine)

## Decisions

### D1: Follow existing test patterns per tier

**Decision**: New tests SHALL replicate the patterns established in existing test files for each tier, rather than introducing new frameworks or conventions.

**Rationale**: The codebase already has well-established patterns — Flask test client for integration tests, pytest-playwright for e2e, `StressTestResult` for stress tests, Node.js `--test` for frontend. Consistency is more valuable than marginal improvements from new tools.

**Alternative considered**: Introducing vitest for frontend tests. Rejected because the Node.js built-in runner is already in use across 23 files and switching would require migrating all existing tests.

### D2: One test file per service/route gap

**Decision**: Each missing test file SHALL cover one service or route module, named following the existing `test_<module_name>.py` convention.

**Rationale**: Maintains 1:1 mapping between source and test files, making it easy to find tests for any given module.

### D3: E2E tests use existing fixture infrastructure

**Decision**: New e2e tests SHALL use the existing `e2e/conftest.py` fixtures (`app_server`, `browser_context_args`) and follow the same page-object-like pattern used in existing e2e tests.

**Rationale**: The e2e infrastructure already handles server URL configuration, browser setup, and locale. No need to create parallel infrastructure.

### D4: Stress tests follow the StressTestResult pattern

**Decision**: New stress tests SHALL use the `StressTestResult` dataclass from `tests/stress/conftest.py` and assert on `success_rate` and `avg_response_time` thresholds.

**Rationale**: Uniform reporting and assertion pattern across all stress tests. The existing dataclass already provides `requests_per_second` and `report()` for diagnostics.

### D5: CI workflow expansion strategy

**Decision**: Extend existing GitHub Actions workflows with additional job steps rather than creating per-feature workflows.

**Rationale**: Two workflows already exist. Adding jobs/steps keeps the CI configuration manageable. Each workflow triggers on relevant path patterns.

## Risks / Trade-offs

- **[E2E tests require running server]** → E2E tests need a live server instance. Mitigation: document required setup in conftest; CI uses existing app_server fixture.
- **[Stress tests are environment-sensitive]** → Results vary by machine. Mitigation: Use generous thresholds (>95% success, <5s avg) and mark as `@pytest.mark.stress` so they run only when explicitly requested.
- **[Large PR size]** → 20-30 new files in one change. Mitigation: Organize by capability (unit, integration, e2e, stress, frontend) so reviewers can focus on one tier at a time.
- **[Flaky e2e tests]** → Browser tests can be timing-sensitive. Mitigation: Use Playwright's built-in auto-waiting; add explicit waits only where necessary; retry once on CI.
