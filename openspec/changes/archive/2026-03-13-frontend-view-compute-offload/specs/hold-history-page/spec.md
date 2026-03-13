## MODIFIED Requirements

### Requirement: Hold History page SHALL display a filter bar with date range and hold type
The page SHALL provide a filter bar for selecting date range and hold type classification. On query, the page SHALL use a two-phase flow: `POST /query` returns `queryId`; subsequent supplementary interactions SHALL prefer local browser-side computation when available and otherwise use `GET /view`.

#### Scenario: Primary query via POST /query
- **WHEN** user clicks the query button (or page loads with default filters)
- **THEN** the page SHALL call `POST /api/hold-history/query` with `{ start_date, end_date, hold_type }`
- **THEN** the response `queryId` SHALL be stored for subsequent interactions
- **THEN** trend, reason-pareto, duration, and list SHALL all be populated from the single response
- **THEN** if the response also includes local-compute eligibility metadata, the page SHALL evaluate whether to activate DuckDB-WASM mode

#### Scenario: Supplementary filter change uses local compute when active
- **WHEN** user changes hold_type, record_type, reason, duration, or pagination while DuckDB-WASM mode is active
- **THEN** the page SHALL recompute trend, reason-pareto, duration, and list locally from the downloaded Parquet spool
- **THEN** no `GET /api/hold-history/view` request SHALL be made
- **THEN** no new Oracle query SHALL be triggered

#### Scenario: Supplementary filter change falls back to GET /view
- **WHEN** user changes hold_type radio or clicks a reason in the Pareto chart while DuckDB-WASM mode is inactive or unavailable
- **THEN** the page SHALL call `GET /api/hold-history/view?query_id=...&hold_type=...&reason=...`
- **THEN** no new Oracle query SHALL be triggered
- **THEN** trend, reason-pareto, duration, and list SHALL update from the view response

#### Scenario: Pagination uses the active compute path
- **WHEN** user navigates to a different page in the detail list
- **THEN** the page SHALL use local pagination when DuckDB-WASM mode is active
- **THEN** otherwise the page SHALL call `GET /api/hold-history/view?query_id=...&page=...&per_page=...`

#### Scenario: Page navigation preserves scroll position
- **WHEN** user clicks Next or Prev in the detail table pagination
- **THEN** data SHALL reload with the updated page number
- **THEN** page scroll position SHALL NOT reset to the top
- **THEN** the table content SHALL remain visible in the DOM during loading
- **THEN** a loading overlay SHALL appear on the table section to indicate progress
- **THEN** SummaryCards, DailyTrend, ReasonPareto, and DurationChart SHALL NOT be refreshed as part of pagination

#### Scenario: Table overlay during pagination
- **WHEN** pagination is in progress
- **THEN** the table rows SHALL be visible but visually dimmed (opacity reduced)
- **THEN** user interaction with table rows SHALL be disabled during loading
- **THEN** once data loads, the overlay SHALL be removed and new rows SHALL display

#### Scenario: Date range change triggers new primary query
- **WHEN** user changes the date range and clicks query
- **THEN** the page SHALL call `POST /api/hold-history/query` with new dates
- **THEN** a new `queryId` SHALL replace the old one
- **THEN** any previous local-compute state SHALL be discarded before evaluating the new response

#### Scenario: Cache expired or spool expired auto-retry
- **WHEN** the page cannot refresh because `GET /view` returns `{ success: false, error: "cache_expired" }` or local spool activation fails with an expiry response
- **THEN** the page SHALL automatically re-execute `POST /api/hold-history/query` with the last committed filters
- **THEN** the view SHALL refresh with the new data

#### Scenario: Department still uses separate API
- **WHEN** department data needs to load or reload
- **THEN** the page SHALL call `GET /api/hold-history/department` separately
