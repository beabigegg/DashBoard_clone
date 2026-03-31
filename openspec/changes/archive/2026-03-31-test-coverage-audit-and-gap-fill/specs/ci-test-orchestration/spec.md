## ADDED Requirements

### Requirement: CI SHALL run all test tiers on relevant path changes
GitHub Actions workflows SHALL be configured so that changes to backend services/routes trigger backend unit and integration tests, changes to frontend sources trigger frontend tests, and changes to e2e/stress infrastructure trigger those respective suites.

#### Scenario: Backend service change triggers unit tests
- **WHEN** a PR modifies files under `src/mes_dashboard/services/` or `src/mes_dashboard/routes/`
- **THEN** the CI workflow SHALL run `pytest tests/ -v --ignore=tests/e2e --ignore=tests/stress`

#### Scenario: Frontend change triggers frontend tests
- **WHEN** a PR modifies files under `frontend/src/`
- **THEN** the CI workflow SHALL run `node --test frontend/tests/*.test.js`

### Requirement: E2E and stress tests SHALL be runnable via CI with explicit triggers
E2E and stress tests SHALL be configurable to run via `workflow_dispatch` or on specific branch patterns, not on every PR.

#### Scenario: E2E tests triggered manually
- **WHEN** a maintainer triggers the e2e workflow via `workflow_dispatch`
- **THEN** the CI SHALL run `pytest tests/e2e/ -v -m e2e`

#### Scenario: Stress tests triggered manually
- **WHEN** a maintainer triggers the stress workflow via `workflow_dispatch`
- **THEN** the CI SHALL run `pytest tests/stress/ -v -m stress` against the configured `STRESS_TEST_URL`

### Requirement: CI SHALL report test results clearly
CI workflows SHALL produce clear pass/fail output and, where possible, include coverage summary information.

#### Scenario: Test failure in CI
- **WHEN** any test fails during a CI run
- **THEN** the workflow SHALL exit with a non-zero status and the failing test name SHALL be visible in the workflow log
