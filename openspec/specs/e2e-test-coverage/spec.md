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

### Requirement: Playwright E2E suite SHALL include API fault-injection coverage

A Playwright spec set SHALL exist under `frontend/tests/playwright/resilience/` that uses `page.route` + `route.fulfill` to inject HTTP failure envelopes from representative API endpoints and verifies that the SPA recovers without leaking loading state, silent failure, or stale data. Fault-injected specs SHALL cover at minimum: server error (5xx), degraded response with `Retry-After` (503), and request abort/timeout.

#### Scenario: 500 response clears loading overlay and shows error toast

- **WHEN** a user submits a query and the backend route is mocked to return `{ status: 500, body: { success: false, error: { code: 'INTERNAL_ERROR', message: '...' } } }`
- **THEN** the loading overlay SHALL disappear within 5 seconds
- **THEN** an error toast or banner SHALL render with the error message
- **THEN** the query button SHALL return to the enabled state
- **THEN** no stale data from a previous query SHALL remain visible

#### Scenario: 503 with Retry-After surfaces degraded UX

- **WHEN** a user submits a query and the backend is mocked to return `{ status: 503, headers: { 'Retry-After': '5' }, body: { success: false, error: { code: 'DB_POOL_EXHAUSTED' } } }`
- **THEN** the UI SHALL display a "系統忙碌請稍候" or equivalent message sourced from the error envelope
- **THEN** any previously rendered results SHALL NOT be replaced by a partial / empty state
- **THEN** the UI SHALL NOT automatically re-submit the query before the `Retry-After` window elapses

#### Scenario: Aborted request releases UI controls

- **WHEN** a user submits a query and the mocked route calls `route.abort('timedout')`
- **THEN** the loading overlay SHALL disappear within 10 seconds
- **THEN** the query button SHALL be enabled for re-submission
- **THEN** the spec SHALL assert no unhandled promise rejection appears in `page.on('pageerror')`

### Requirement: Playwright E2E suite SHALL verify loading UX under slow network

A Playwright spec at `frontend/tests/playwright/resilience/slow-network.spec.js` SHALL simulate delayed API responses via `page.route` + `await new Promise(r => setTimeout(r, N))` before `route.continue()` and SHALL verify that the three-tier loading policy (page / block / button) behaves correctly.

#### Scenario: Page-level loading overlay appears during 5-second delayed query

- **WHEN** a primary query API is mocked with a 5-second delay before response
- **THEN** within 500ms of submit, the page-tier `LoadingOverlay` SHALL be visible
- **THEN** after the response resolves, the overlay SHALL disappear within 500ms
- **THEN** the DOM SHALL not emit `prefers-reduced-motion`-ignoring animations (visual check via CSS `animation` computed style)

#### Scenario: Button busy state matches in-flight request

- **WHEN** a button-initiated action API is mocked with a 3-second delay
- **THEN** the initiating button SHALL have `aria-busy="true"` and disabled state for the duration of the request
- **THEN** after response, `aria-busy` SHALL return to `false` and the button SHALL be re-enabled

### Requirement: Playwright E2E suite SHALL verify rapid-interaction and concurrent-action guards

A Playwright spec at `frontend/tests/playwright/resilience/rapid-interaction.spec.js` SHALL verify that the SPA guards against double-submit, concurrent export/query actions, and in-flight query cancellation via the `useRequestGuard` composable.

#### Scenario: Double-click on query button issues only one API request

- **WHEN** a user clicks the query button 5 times within 200ms
- **THEN** exactly 1 matching API request SHALL be observed by `page.on('request')`
- **THEN** no duplicated result rendering SHALL occur

#### Scenario: Export action is blocked while query is in flight

- **WHEN** a query is in flight (loading overlay visible) and the user clicks the export button
- **THEN** the export button SHALL either be disabled, or a guard toast SHALL indicate "查詢進行中無法匯出"
- **THEN** no `/api/.../export` or spool-triggering request SHALL be fired

#### Scenario: Concurrent export clicks deduplicate

- **WHEN** export button is clicked 3 times within 300ms after a completed query
- **THEN** at most 1 download event SHALL be observed
- **THEN** no partial / corrupted file SHALL be downloaded

### Requirement: Playwright E2E suite SHALL verify browser history and mid-flow reload

A Playwright spec at `frontend/tests/playwright/resilience/browser-history.spec.js` SHALL exercise browser back/forward navigation and reload during active query lifecycles, asserting that URL-state survives and cross-page leakage does not occur.

#### Scenario: Back button restores prior URL state after cross-page navigation

- **WHEN** page A captures filters into URL state, then user navigates via sidebar to page B, then presses browser back
- **THEN** `page.goBack()` SHALL land on page A
- **THEN** page A's filter inputs SHALL repopulate from the restored URL state
- **THEN** no console error SHALL indicate `undefined`/`null` filter values

#### Scenario: Forward button re-lands on page B after back

- **WHEN** the user is on page A after a back navigation, then presses browser forward
- **THEN** `page.goForward()` SHALL land on page B
- **THEN** page B's prior state SHALL be restored (including any query result view)

#### Scenario: Reload during in-flight query does not corrupt state

- **WHEN** a user submits a query and calls `page.reload()` within 500ms of submit (while loading overlay is visible)
- **THEN** after reload, the page SHALL either (a) re-submit the query automatically from URL state, or (b) render the idle form with URL-restored filters
- **THEN** no orphaned "請求中" / loading indicator SHALL persist indefinitely

### Requirement: Playwright E2E suite SHALL exercise malformed user input at browser layer

A Playwright spec at `frontend/tests/playwright/data-boundary/malformed-input.spec.js` SHALL feed representative malicious/edge input into primary query pages (Query Tool, Reject History) and assert the UI either blocks locally or receives a well-formed `VALIDATION_ERROR` envelope.

#### Scenario: SQL-style payload is rejected with VALIDATION_ERROR

- **WHEN** the Query Tool textarea is filled with `LOT-001'; DROP TABLE--` and submitted
- **THEN** either the client validator SHALL block the submit with an inline message, or the API SHALL respond with `{ success: false, error: { code: 'VALIDATION_ERROR' } }`
- **THEN** no 500 response and no white screen SHALL occur

#### Scenario: Extremely long input is bounded by URL guard

- **WHEN** a user pastes a 100,000-character string into a filter input and submits
- **THEN** either client-side length validation SHALL reject the submit, or the API SHALL respond with `VALIDATION_ERROR` / `URL_TOO_LONG`
- **THEN** the browser SHALL NOT throw `QuotaExceededError` on URL state persistence

#### Scenario: Unicode / emoji input is handled without crash

- **WHEN** the user enters `LOT-🚀-測試-ñoño` into a query input and submits
- **THEN** the request SHALL be sent with correctly UTF-8 encoded parameters
- **THEN** the response SHALL be a normal success envelope or `VALIDATION_ERROR`, never a 500 or encoding error banner

#### Scenario: Inverted date range triggers validation error

- **WHEN** start date = 2026-03-15 and end date = 2026-03-01 and submit is clicked
- **THEN** the UI SHALL block submission with an inline validation message OR the API SHALL respond with `VALIDATION_ERROR`
- **THEN** no query SHALL reach Oracle with the inverted range

### Requirement: Playwright E2E suite SHALL verify empty-result rendering across pages

A Playwright spec at `frontend/tests/playwright/data-boundary/empty-result.spec.js` SHALL mock primary query APIs to return a well-formed empty envelope (`{ success: true, data: [] }` or domain-equivalent) and assert each page renders a proper empty state rather than leaving a blank canvas.

#### Scenario: Hold Overview renders empty state when treemap data is empty

- **WHEN** `/api/hold/treemap` is mocked to return an empty items array
- **THEN** the empty-state placeholder component SHALL render with user-visible copy
- **THEN** no treemap / chart shell SHALL render with 0 rects (no ghost SVG)

#### Scenario: Reject History renders empty state when result rows are empty

- **WHEN** `/api/reject-history/query` is mocked to return `{ success: true, data: { rows: [], pagination: { total_count: 0 } } }`
- **THEN** the result area SHALL render `.empty-state` with descriptive copy
- **THEN** export / CSV button SHALL be disabled or labelled "無資料可匯出"

#### Scenario: Query Tool renders empty state for empty equipment list

- **WHEN** the equipment list API is mocked to return an empty array
- **THEN** the page SHALL display a "無符合結果" type message
- **THEN** no empty table shell with only headers SHALL render without the empty-state message

### Requirement: Playwright resilience helpers SHALL be shared through `_auth.js`

The shared Playwright helper module `frontend/tests/playwright/_auth.js` SHALL export a `mockApiError(page, urlPattern, status, options)` function so that resilience specs do not duplicate `page.route` + `route.fulfill` boilerplate. Options SHALL support `{ body, delay, headers }`.

#### Scenario: Helper exposes mockApiError

- **WHEN** a spec imports `mockApiError` from `_auth.js`
- **THEN** calling `mockApiError(page, '**/api/foo', 500)` SHALL register a `page.route` that fulfills with status 500 and a default error envelope sourced from `core/response.py` error code constants

#### Scenario: Helper supports delayed responses

- **WHEN** `mockApiError(page, '**/api/foo', 200, { delay: 3000, body: {...} })` is called
- **THEN** the mocked response SHALL be delayed by 3 seconds before delivery
- **THEN** the helper SHALL still resolve within the Playwright test timeout

### Requirement: Resilience and data-boundary specs SHALL include mutation-check verification

Each new Playwright resilience / data-boundary spec SHALL be accompanied by a documented mutation-check procedure in the PR description: temporarily removing the corresponding frontend error handler or guard SHALL cause the spec to FAIL. Specs that still pass after the guard is removed SHALL be rejected in code review.

#### Scenario: Mutation check documented in PR

- **WHEN** a new resilience spec is submitted
- **THEN** the PR description SHALL list the specific handler / guard removal tested
- **THEN** the reviewer SHALL verify the FAIL outcome before approving

