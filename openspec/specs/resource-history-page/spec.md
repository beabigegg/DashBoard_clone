## Purpose
Define stable requirements for resource-history-page.

## Requirements

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

### Requirement: Resource History page SHALL display KPI summary cards
The page SHALL show 9 KPI cards with aggregated performance metrics derived from the cached dataset.

#### Scenario: KPI cards from cached data
- **WHEN** summary data is derived from the cached DataFrame
- **THEN** 9 cards SHALL display: OU%, AVAIL%, PRD, SBY, UDT, SDT, EGT, NST, Machine Count
- **THEN** values SHALL be computed from the cached shift-status records, not from a separate Oracle query

### Requirement: Resource History page SHALL display hierarchical detail table
The page SHALL show a three-level expandable table derived from the cached dataset.

#### Scenario: Detail table from cached data
- **WHEN** detail data is derived from the cached DataFrame
- **THEN** a tree table SHALL display with the same columns and hierarchy as before
- **THEN** data SHALL be derived in-memory from the cached DataFrame, not from a separate Oracle query

### Requirement: Database query execution path
The resource-history service (`resource_history_service.py`) SHALL use `read_sql_df_slow` (dedicated connection) instead of `read_sql_df` (pooled connection) for all Oracle queries.

#### Scenario: Summary parallel queries use dedicated connections
- **WHEN** the resource-history summary query executes 3 parallel queries via ThreadPoolExecutor
- **THEN** each query uses `read_sql_df_slow` and acquires a semaphore slot
- **AND** all 3 queries complete and release their slots

### Requirement: Frontend timeout
The resource-history page frontend SHALL use a 360-second API timeout for all Oracle-backed API calls.

#### Scenario: Large date range query completes
- **WHEN** a user queries resource history for a 2-year date range
- **THEN** the frontend does not abort the request for at least 360 seconds
