## ADDED Requirements

### Requirement: Playwright real-browser E2E SHALL cover three high-value flows
A Playwright test suite SHALL run against the running application using the shared browser cache at `~/.cache/ms-playwright`, covering the three highest-value user flows.

#### Scenario: Hold Overview flow
- **WHEN** the Playwright `hold-overview.spec.js` runs
- **THEN** it SHALL log in, open Hold Overview, drill into a treemap node, and export CSV, asserting each step completes without JS runtime errors

#### Scenario: Reject History async flow
- **WHEN** the Playwright `reject-history.spec.js` runs
- **THEN** it SHALL log in, submit a large-range query that produces HTTP 202, poll to completion, and download the spool result

#### Scenario: Query Tool flow
- **WHEN** the Playwright `query-tool.spec.js` runs
- **THEN** it SHALL log in, enter a query, execute it, materialise the result, and export

### Requirement: Playwright suite SHALL reuse the shared browser cache
The Playwright configuration SHALL point at `~/.cache/ms-playwright` and SHALL NOT invoke `playwright install`.

#### Scenario: No reinstall triggered
- **WHEN** the Playwright suite is configured and run
- **THEN** the configuration SHALL resolve browsers from the shared cache
- **THEN** no command SHALL execute `playwright install`

### Requirement: In-process Flask e2e tests SHALL remain the pre-merge gate
The existing `tests/e2e/*.py` Flask-client e2e tests SHALL remain the fast pre-merge gate while Playwright E2E runs nightly.

#### Scenario: Pre-merge runs Flask e2e
- **WHEN** pre-merge CI runs
- **THEN** `pytest --run-e2e tests/e2e/` SHALL execute and gate the merge

#### Scenario: Nightly adds Playwright
- **WHEN** nightly CI runs
- **THEN** the Playwright suite SHALL execute in addition to pytest `--run-integration` and `--run-e2e`
