## MODIFIED Requirements

### Requirement: Resource History page SHALL support date range and granularity selection
The page SHALL allow users to specify time range and aggregation granularity. On query, the page SHALL use a two-phase flow: `POST /query` returns `queryId`; subsequent supplementary interactions SHALL prefer local browser-side computation when available and otherwise use `GET /view`.

#### Scenario: Primary query via POST /query
- **WHEN** user clicks the query button
- **THEN** the page SHALL call `POST /api/resource/history/query` with date range, granularity, and resource filters
- **THEN** the response `queryId` SHALL be stored for subsequent interactions
- **THEN** summary (KPI, trend, heatmap, comparison) and detail page 1 SHALL all be populated from the single response
- **THEN** if the response also includes local-compute eligibility metadata, the page SHALL evaluate whether to activate DuckDB-WASM mode

#### Scenario: Supplementary filter change uses local compute when active
- **WHEN** user changes supplementary filters while DuckDB-WASM mode is active
- **THEN** the page SHALL recompute summary and detail locally from the downloaded Parquet spool
- **THEN** no `GET /api/resource/history/view` request SHALL be made
- **THEN** no new Oracle query SHALL be triggered

#### Scenario: Supplementary filter change falls back to GET /view
- **WHEN** user changes supplementary filters while DuckDB-WASM mode is inactive or unavailable
- **THEN** the page SHALL call `GET /api/resource/history/view?query_id=...&filters...`
- **THEN** no new Oracle query SHALL be triggered
- **THEN** all charts, KPI cards, and detail table SHALL update from the view response

#### Scenario: Pagination uses the active compute path
- **WHEN** user navigates to a different page in the detail table
- **THEN** the page SHALL use local pagination when DuckDB-WASM mode is active
- **THEN** otherwise the page SHALL call `GET /api/resource/history/view?query_id=...&page=...`

#### Scenario: Date range or granularity change triggers new primary query
- **WHEN** user changes date range or granularity and clicks query
- **THEN** the page SHALL call `POST /api/resource/history/query` with new params
- **THEN** a new `queryId` SHALL replace the old one
- **THEN** any previous local-compute state SHALL be discarded before evaluating the new response

#### Scenario: Cache expired or spool expired auto-retry
- **WHEN** the page cannot refresh because `GET /view` returns `{ success: false, error: "cache_expired" }` or local spool activation fails with an expiry response
- **THEN** the page SHALL automatically re-execute `POST /api/resource/history/query` with the last committed filters
- **THEN** the view SHALL refresh with the new data
