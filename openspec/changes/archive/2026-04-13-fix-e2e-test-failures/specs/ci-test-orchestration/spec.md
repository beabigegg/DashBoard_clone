## ADDED Requirements

### Requirement: E2E tests SHALL run sequentially when targeting multiple environments
When e2e tests are executed against both local and remote targets in a single workflow / session, the runs SHALL be sequential (local first, then remote), not concurrent, to avoid Chromium process contention and memory exhaustion on shared runners.

#### Scenario: Dual-target e2e execution via script
- **WHEN** a maintainer runs `./scripts/run_e2e.sh` with `E2E_REMOTE_URL` set
- **THEN** the script SHALL first run `pytest tests/e2e -m e2e --run-e2e` against `http://127.0.0.1:8080`, and only after it completes (pass or fail) SHALL run the same suite against `$E2E_REMOTE_URL`

#### Scenario: Single-target e2e execution
- **WHEN** `E2E_REMOTE_URL` is not set
- **THEN** the script SHALL run e2e tests against the local target only and exit

### Requirement: E2E suite SHALL support local_only marker for worker-state-dependent tests
The test infrastructure SHALL provide a `local_only` pytest marker. Tests marked `local_only` SHALL be automatically skipped when `E2E_BASE_URL` points to an external deployment (i.e., `_is_external_e2e_target()` returns True), so that tests requiring in-process RQ worker state (e.g., trace pipeline 409 pre-completion checks) do not produce false failures against remote environments.

#### Scenario: local_only marker registered in pytest.ini
- **WHEN** pytest is configured for this repo
- **THEN** `pytest.ini` SHALL register the `local_only` marker with a description indicating it is for in-process-worker-dependent tests

#### Scenario: Autouse skip fixture applies the marker
- **WHEN** an e2e test marked `@pytest.mark.local_only` is collected
- **AND** `E2E_BASE_URL` resolves to a non-localhost host
- **THEN** an autouse fixture in `tests/e2e/conftest.py` SHALL call `pytest.skip("local_only: requires in-process worker state")` for that test

#### Scenario: Trace pipeline tests marked local_only
- **WHEN** the `test_trace_pipeline_e2e.py` module is collected
- **THEN** all tests in that module SHALL carry the `local_only` marker (either at module or class level)
