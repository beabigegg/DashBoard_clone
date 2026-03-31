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
The page SHALL show 10 KPI cards with aggregated performance metrics derived from the cached dataset, including OEE%.

#### Scenario: KPI cards from cached data
- **WHEN** summary data is derived from the cached DataFrame
- **THEN** 10 cards SHALL display in order: OU%, OEE%, AVAIL%, PRD, SBY, UDT, SDT, EGT, NST, Machine Count
- **THEN** the OEE% card SHALL show the computed OEE percentage
- **THEN** the OEE% card SHALL use accent coloring consistent with the OU% card logic
- **THEN** values SHALL be computed from the cached shift-status records combined with OEE production/NG data

### Requirement: Resource History page SHALL display hierarchical detail table
The page SHALL show a three-level expandable table derived from the cached dataset, including OEE% column.

#### Scenario: Detail table from cached data
- **WHEN** detail data is derived from the cached DataFrame
- **THEN** a tree table SHALL display with existing columns plus an OEE% column
- **THEN** OEE% column SHALL appear between OU% and AVAIL% columns
- **THEN** each row SHALL show the OEE% computed from that resource's availability and yield data
- **THEN** if a resource has no production data (trackout + ng = 0), OEE% SHALL display as "—"

### Requirement: Resource History trend chart SHALL overlay OEE% line
The trend chart SHALL display an OEE% line alongside existing OU% and AVAIL% lines.

#### Scenario: OEE% trend line rendering
- **WHEN** trend data includes OEE metrics per period
- **THEN** the chart SHALL render an OEE% line with a distinct color from OU% and AVAIL%
- **THEN** the OEE% line SHALL use the same Y-axis scale (0-100%) as other percentage lines
- **THEN** the legend SHALL include an OEE% entry

### Requirement: Resource History heatmap SHALL support metric toggle
The heatmap SHALL allow switching between OU%, OEE%, and AVAIL% metrics.

#### Scenario: Heatmap metric selection
- **WHEN** user selects a different metric from the heatmap dropdown
- **THEN** the heatmap cells SHALL recalculate using the selected metric
- **THEN** the color scale SHALL adjust to the selected metric's value range
- **THEN** the default metric SHALL be OU%
- **THEN** no additional API call SHALL be made — data for all metrics SHALL be present in the existing response

### Requirement: CSV export SHALL include OEE% column
The CSV export SHALL include OEE-related fields alongside existing columns.

#### Scenario: Export with OEE data
- **WHEN** user exports resource history data to CSV
- **THEN** the CSV SHALL include columns: `OEE%`, `Yield%`, `TRACKOUT_QTY`, `NG_QTY`
- **THEN** OEE% SHALL appear between OU% and AVAIL%, followed by Yield%, TRACKOUT_QTY, NG_QTY after AVAIL% (matching the KPI card and detail table column order)

### Requirement: Database query execution path
The resource-history service SHALL use `read_sql_df_slow` (dedicated connection) for all Oracle queries. The canonical spool path (`try_compute_query_from_canonical_spool`) SHALL be attempted first on every POST /query; if the spool is valid the Oracle path SHALL be skipped entirely. The spool validity window SHALL be governed by `CACHE_TTL_DATASET_SECONDS` (default 7200 seconds).

#### Scenario: Canonical spool hit skips Oracle
- **WHEN** POST /query is received and the canonical spool for the requested date range exists in Redis
- **THEN** `try_compute_query_from_canonical_spool()` SHALL return a non-None result
- **THEN** no Oracle query SHALL be executed
- **THEN** the response SHALL be returned within the DuckDB computation time (no Oracle latency)

#### Scenario: Spool remains valid across warmup cycles
- **WHEN** `CACHE_TTL_DATASET_SECONDS=7200` and `WARMUP_INTERVAL_SECONDS=3600`
- **THEN** a spool created by warmup SHALL remain valid until the next warmup fires and refreshes it
- **THEN** users querying between warmup cycles SHALL receive the cached spool, not trigger Oracle

#### Scenario: Canonical spool miss falls through to Oracle
- **WHEN** the canonical spool Redis metadata key is absent or expired
- **THEN** `execute_primary_query()` SHALL run Oracle queries
- **THEN** the result SHALL be spooled to Parquet and registered with TTL=`CACHE_TTL_DATASET_SECONDS`

#### Scenario: Summary parallel queries use dedicated connections
- **WHEN** the resource-history summary query executes parallel queries via ThreadPoolExecutor
- **THEN** each query uses `read_sql_df_slow` and acquires a semaphore slot
- **AND** all queries complete and release their slots

### Requirement: Frontend timeout
The resource-history page frontend SHALL use a 360-second API timeout for all Oracle-backed API calls.

#### Scenario: Large date range query completes
- **WHEN** a user queries resource history for a 2-year date range
- **THEN** the frontend does not abort the request for at least 360 seconds
