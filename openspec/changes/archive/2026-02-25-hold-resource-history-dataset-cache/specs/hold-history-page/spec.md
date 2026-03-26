## MODIFIED Requirements

### Requirement: Hold History page SHALL display a filter bar with date range and hold type
The page SHALL provide a filter bar for selecting date range and hold type classification. On query, the page SHALL use a two-phase flow: POST /query returns queryId, subsequent filter changes use GET /view.

#### Scenario: Primary query via POST /query
- **WHEN** user clicks the query button (or page loads with default filters)
- **THEN** the page SHALL call `POST /api/hold-history/query` with `{ start_date, end_date, hold_type }`
- **THEN** the response queryId SHALL be stored for subsequent view requests
- **THEN** trend, reason-pareto, duration, and list SHALL all be populated from the single response

#### Scenario: Hold type or reason filter change uses GET /view
- **WHEN** user changes hold_type radio or clicks a reason in the Pareto chart (while queryId exists)
- **THEN** the page SHALL call `GET /api/hold-history/view?query_id=...&hold_type=...&reason=...`
- **THEN** no new Oracle query SHALL be triggered
- **THEN** trend, reason-pareto, duration, and list SHALL update from the view response

#### Scenario: Pagination uses GET /view
- **WHEN** user navigates to a different page in the detail list
- **THEN** the page SHALL call `GET /api/hold-history/view?query_id=...&page=...&per_page=...`

#### Scenario: Date range change triggers new primary query
- **WHEN** user changes the date range and clicks query
- **THEN** the page SHALL call `POST /api/hold-history/query` with new dates
- **THEN** a new queryId SHALL replace the old one

#### Scenario: Cache expired auto-retry
- **WHEN** GET /view returns `{ success: false, error: "cache_expired" }`
- **THEN** the page SHALL automatically re-execute `POST /api/hold-history/query` with the last committed filters
- **THEN** the view SHALL refresh with the new data

#### Scenario: Department still uses separate API
- **WHEN** department data needs to load or reload
- **THEN** the page SHALL call `GET /api/hold-history/department` separately
