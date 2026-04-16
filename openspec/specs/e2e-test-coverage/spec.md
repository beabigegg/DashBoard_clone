## Purpose

Ensure every user-facing page has at least one e2e test exercising the primary user workflow.
## Requirements
### Requirement: Every user-facing page SHALL have at least one e2e test
Each frontend SPA application that represents a user-facing page SHALL have a corresponding `tests/e2e/test_<page>_e2e.py` file exercising the primary user workflow.

#### Scenario: Page with no existing e2e test gets coverage
- **WHEN** a page exists as a frontend SPA application with no corresponding e2e test
- **THEN** an e2e test file SHALL be created that navigates to the page, verifies it loads, and exercises the primary query/filter workflow

#### Scenario: Identified gap pages
- **WHEN** auditing the following pages: `production-history`, `anomaly-overview`, `admin-dashboard`, `admin-performance`, `admin-user-usage-kpi`
- **THEN** each SHALL have a dedicated e2e test file

### Requirement: E2E tests SHALL use existing playwright fixtures
All new e2e tests SHALL use the `app_server`, `browser_context_args`, and `api_base_url` fixtures from `tests/e2e/conftest.py`.

#### Scenario: New e2e test setup
- **WHEN** a new e2e test file is created
- **THEN** it SHALL import and use the shared e2e conftest fixtures for server URL and browser configuration

### Requirement: E2E tests SHALL verify page load and primary content
Each e2e test SHALL at minimum verify that the page loads without JavaScript errors and that the primary content area renders.

#### Scenario: Page loads successfully
- **WHEN** the e2e test navigates to the page URL
- **THEN** the page SHALL render without console errors and the main content container SHALL be visible

#### Scenario: Primary query workflow
- **WHEN** the page has a query/filter form
- **THEN** the e2e test SHALL fill the form, submit, and verify that results appear in the data area

### Requirement: Admin E2E tests SHALL disable automatic redirect following
All e2e tests that exercise `/admin/api/*` endpoints SHALL pass `allow_redirects=False` to `requests.get()` / `requests.post()` calls to prevent the client from following the `before_request` hook's 302 redirect to `/portal-shell/`, which would otherwise deliver an HTML body that breaks subsequent `resp.json()` calls.

#### Scenario: Unauthenticated admin API call preserves 302
- **WHEN** an admin e2e test calls `requests.get(f"{app_server}/admin/api/...", allow_redirects=False)` without an active admin session
- **THEN** the response status SHALL be 302 (or 401/403) and the test SHALL assert `resp.status_code in (200, 302, 401, 403)` without attempting to parse JSON

#### Scenario: Authenticated admin API call receives 200 JSON
- **WHEN** an admin e2e test calls an admin API endpoint with a valid admin session
- **THEN** the response status SHALL be 200 and the test MAY call `resp.json()` to inspect the success envelope

### Requirement: Browser E2E tests SHALL use explicit visibility waits
Playwright-based e2e tests SHALL use `expect(locator).to_be_visible(timeout=...)` or `page.expect_response(...)` context managers for element / network waits, and SHALL NOT rely on fixed `page.wait_for_timeout(N)` sleeps as the primary synchronization mechanism.

#### Scenario: Query-tool textarea wait after tab activation
- **WHEN** a test navigates to `/portal-shell/query-tool?tab=lot`
- **THEN** the test SHALL wait via `expect(page.locator("textarea.query-tool-textarea:visible").first).to_be_visible(timeout=30000)` before interacting with the textarea

#### Scenario: Hold-detail API observation uses response helper
- **WHEN** a test verifies that `/api/wip/hold-detail/{summary,distribution,lots}` are all called
- **THEN** the test SHALL use the `_wait_for_response` helper with endpoint-specific predicates rather than a custom polling loop over a `seen` set

### Requirement: E2E assertions SHALL match current API response envelope
E2E tests that inspect response bodies SHALL assert against the actual `success_response` envelope shape (`{"data": ..., "meta": ..., "success": true}`) where `data` may be a dict containing `items`, not historical shapes.

#### Scenario: Type options endpoint
- **WHEN** `GET /api/production-history/type-options` returns `{"data": {"items": [...]}, "success": true}`
- **THEN** the test assertion SHALL be `isinstance(data, dict) and isinstance(data.get("items"), list)`, not `isinstance(data, list) or "pj_types" in data`

### Requirement: E2E tests SHALL accept async 202 where the API legitimately returns it
E2E tests calling endpoints that may legitimately return HTTP 202 (async enqueue on cache miss) SHALL include 202 in the expected status set.

#### Scenario: Yield-alert summary within limit
- **WHEN** `GET /api/yield-alert/summary` is called with a valid date range
- **THEN** the test SHALL assert `resp.status_code in (200, 202)` to accept both sync (cache hit) and async (cache miss) outcomes

### Requirement: E2E test data pickers SHALL skip on empty upstream data
Helper functions that select real data (e.g., `_pick_hold_reason`, `_pick_workcenter`) SHALL detect empty upstream responses and raise `pytest.skip(...)` with a clear message instead of returning a fallback that leads to downstream assertion failures.

#### Scenario: Hold reasons list is empty
- **WHEN** `_pick_hold_reason(app_server)` receives a response whose `data.items` is empty or missing
- **THEN** the helper SHALL call `pytest.skip("No hold reason data available for E2E test")`

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

