## Purpose

Ensure every frontend SPA module with business logic has at least one test file covering its composables and utilities.
## Requirements
### Requirement: Every frontend SPA module SHALL have at least one test file
Each frontend SPA application under `frontend/src/` that contains composables, utilities, or significant business logic SHALL have a corresponding test file in `frontend/tests/`.

#### Scenario: SPA module with no existing test gets coverage
- **WHEN** a frontend SPA module exists with composables or business logic and no corresponding test file
- **THEN** a test file SHALL be created covering the primary composable or utility functions

#### Scenario: Identified gap modules
- **WHEN** auditing the following frontend modules: `resource-status`, `resource-history`, `production-history`, `admin-dashboard`, `admin-performance`, `admin-user-usage-kpi`, `anomaly-overview`, `mid-section-defect` (composable-level), `material-trace` (composable-level)
- **THEN** each SHALL have at least one test file exercising its key logic

### Requirement: Frontend tests SHALL use Node.js built-in test runner
All new frontend tests SHALL use `node:test` and `node:assert` modules, consistent with the existing test files.

#### Scenario: New frontend test file
- **WHEN** a new test file is created in `frontend/tests/`
- **THEN** it SHALL import from `node:test` (describe, it) and `node:assert` (strict)

### Requirement: Frontend tests SHALL cover data transformation logic
For modules that transform API responses into display data, tests SHALL verify the transformation produces correct output for representative inputs.

#### Scenario: Composable transforms API data
- **WHEN** a composable function receives an API response object
- **THEN** the test SHALL verify the transformed output matches expected display values

#### Scenario: Edge case handling
- **WHEN** a composable receives empty, null, or malformed input
- **THEN** the test SHALL verify graceful handling without throwing

### Requirement: Frontend test runner SHALL support Vue SFC component mounting
The frontend test stack SHALL migrate from `node --test` to Vitest + @vue/test-utils + jsdom to enable mounting `.vue` components in tests.

#### Scenario: Vitest runs existing composable tests
- **WHEN** `npm test` is executed
- **THEN** Vitest SHALL run all migrated tests from the existing `tests/` directory
- **THEN** any incompatible legacy tests SHALL remain under `tests/legacy/` and run via a separate script during the transition

#### Scenario: Vue SFC mount works in jsdom
- **WHEN** a test mounts a `.vue` component via `@vue/test-utils`
- **THEN** the component SHALL render into jsdom and expose interactive queries for assertions

### Requirement: High-risk shared components SHALL have unit tests
The following components SHALL each have a Vitest test file exercising empty state, malformed input, and the primary interaction pattern.

#### Scenario: DataTable guards malformed pagination
- **WHEN** `DataTable` receives `pagination.page = 'abc'`
- **THEN** it SHALL NOT render `NaN` in the page indicator AND SHALL fall back to page 1

#### Scenario: LoadingOverlay and LoadingSpinner tier compliance
- **WHEN** the tier prop is set to `page`, `section`, or `block`
- **THEN** the correct DOM structure and `aria-busy` attribute SHALL be emitted per the three-tier policy

#### Scenario: FilterPanel resilient to missing options
- **WHEN** upstream options return `{}` or an empty array
- **THEN** `FilterPanel` SHALL render an empty dropdown without throwing

#### Scenario: HoldMatrix renders missing children as empty
- **WHEN** a treemap node lacks the `children` key
- **THEN** `HoldMatrix` SHALL treat it as a leaf and render without error

#### Scenario: ParetoGrid handles missing aggregate keys
- **WHEN** `by_reason` or `by_package` is absent from the response
- **THEN** `ParetoGrid` SHALL render an empty state without crashing

#### Scenario: DateRangePicker enforces upper bound
- **WHEN** a user attempts to select a range exceeding the configured maximum
- **THEN** the confirm button SHALL be disabled AND a tooltip SHALL explain the limit

#### Scenario: ActionButton prevents double-click
- **WHEN** a user rapidly clicks an `ActionButton` in its loading state
- **THEN** only one click handler invocation SHALL occur

### Requirement: AbortController regressions SHALL be covered by dedicated tests
A test file SHALL exist for every composable touched by commit `e76be26` (yield-alert, reject-history, production-history, query-tool).

#### Scenario: Unmount aborts pending fetch
- **WHEN** a composable mounts, triggers a fetch, and unmounts before the fetch resolves
- **THEN** the underlying fetch SHALL have been called with an `AbortSignal` AND `signal.aborted` SHALL be true

#### Scenario: No state mutation after unmount
- **WHEN** a fetch resolves after the composable unmounts
- **THEN** no reactive state SHALL be updated

### Requirement: Per-composable validation sweeps SHALL catch malformed API responses
Each high-risk composable SHALL have a `*.validation.test.js` file that feeds malformed payloads and asserts non-crash, neutral-empty-state, and DEV warning behaviour.

#### Scenario: Composable survives missing pagination
- **WHEN** a composable receives a response missing `pagination`
- **THEN** it SHALL return a neutral empty state AND emit a DEV warning AND SHALL NOT throw

#### Scenario: Composable survives non-array rows
- **WHEN** `rows` is `null` or a string
- **THEN** the composable SHALL default to `[]` AND emit a DEV warning

### Requirement: Shared composables SHALL have lifecycle tests
`useAutoRefresh`, `useRequestGuard`, and `useAsyncJobPolling` SHALL each have dedicated lifecycle tests.

#### Scenario: useAutoRefresh timer stopped on session expiry
- **WHEN** the polling response returns `SESSION_EXPIRED`
- **THEN** `useAutoRefresh` SHALL stop its timer and not re-poll

#### Scenario: useRequestGuard drops stale responses
- **WHEN** a stale response resolves after a newer request has been issued
- **THEN** the stale result SHALL NOT update composable state

#### Scenario: useAsyncJobPolling grace-retries transient not_found
- **WHEN** an initial poll returns `not_found` within 500ms of job submission
- **THEN** the composable SHALL retry up to 3 times before surfacing an error

