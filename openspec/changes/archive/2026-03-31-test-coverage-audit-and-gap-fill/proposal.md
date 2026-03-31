## Why

The MES Dashboard has grown to 57 backend services, 23 route modules, and 20 frontend applications. While 155 backend test files and 23 frontend test files exist, there is no systematic audit confirming that every service, route, and frontend feature has adequate coverage across all test tiers (unit, integration, e2e, stress). Known gaps include missing stress tests for several high-traffic endpoints, incomplete e2e coverage for newer pages (anomaly-overview, admin-user-usage-kpi, production-history), and no frontend component-level tests for many SPA modules. Filling these gaps now prevents regressions as the codebase continues to expand.

## What Changes

- **Audit existing coverage**: Produce a coverage matrix mapping every service, route, and frontend app to its test files across all four tiers (unit, integration, e2e, stress).
- **Add missing backend unit tests**: Fill gaps for services lacking dedicated test files (e.g., `sql_fragments.py`, `user_usage_kpi_service.py`, `anomaly_detection_sql_runtime.py`, `material_trace_duckdb_runtime.py`).
- **Add missing backend integration tests**: Ensure every route module has corresponding integration tests that exercise the full request-response cycle with mocked or real dependencies.
- **Add missing e2e tests**: Cover pages currently without e2e tests: `production-history`, `anomaly-overview`, `admin-user-usage-kpi`, `admin-performance`, `admin-dashboard`.
- **Add missing frontend tests**: Add test files for frontend apps that lack them (resource-status, resource-history, production-history, admin modules, anomaly-overview, mid-section-defect composables).
- **Expand stress tests**: Add stress test scenarios for material-trace, mid-section-defect, yield-alert, resource-history, and production-history endpoints.
- **CI integration**: Extend GitHub Actions workflows to run the full test suite on relevant path triggers.

## Capabilities

### New Capabilities
- `backend-unit-test-coverage`: Audit and gap-fill for backend service-level unit tests
- `backend-integration-test-coverage`: Audit and gap-fill for route-level integration tests
- `e2e-test-coverage`: Audit and gap-fill for end-to-end browser tests across all pages
- `stress-test-coverage`: Audit and gap-fill for load/stress tests on high-traffic endpoints
- `frontend-test-coverage`: Audit and gap-fill for frontend component and composable tests
- `ci-test-orchestration`: CI workflow updates to ensure all test tiers run on relevant changes

### Modified Capabilities
_(none — no existing spec-level requirements are changing)_

## Impact

- **Test files**: ~20-30 new test files across `tests/`, `tests/e2e/`, `tests/stress/`, `frontend/tests/`
- **Dependencies**: May need `pytest-cov` for coverage reporting; no other new dependencies expected
- **CI/CD**: `.github/workflows/` will gain new or expanded workflow definitions
- **Runtime**: No production code changes — test-only
