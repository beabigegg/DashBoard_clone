## ADDED Requirements

### Requirement: Frontend SHALL load DuckDB-WASM in a Web Worker for client-side SQL computation
The frontend SHALL initialize DuckDB-WASM inside a dedicated Web Worker to execute SQL queries against Parquet data without blocking the UI thread.

#### Scenario: DuckDB-WASM initialization
- **WHEN** a report page determines that client-side computation is needed
- **THEN** the system SHALL lazily initialize DuckDB-WASM in a Web Worker (one-time per session)
- **THEN** the WASM bundle SHALL be cached by the browser for subsequent loads

#### Scenario: Web Worker message protocol
- **WHEN** the main thread sends a query request to the Worker
- **THEN** the Worker SHALL accept messages with `{ type: 'query', sql: string, parquetUrl: string }`
- **THEN** the Worker SHALL respond with `{ type: 'result', data: Array }` or `{ type: 'error', message: string }`

### Requirement: Frontend SHALL download Parquet spool files and register them in DuckDB-WASM
The frontend SHALL fetch Parquet files from the spool download API and register them as DuckDB tables for local querying.

#### Scenario: Parquet download and registration after query or view response
- **WHEN** a report page response includes `spool_download_url` and the dataset exceeds the local-compute threshold
- **THEN** the frontend SHALL download the Parquet file via fetch()
- **THEN** the Parquet file SHALL be registered in the DuckDB-WASM instance as a named table
- **THEN** subsequent filter/sort/page operations SHALL query this local table instead of calling the server `/view` API

#### Scenario: Resource History and Hold History activate from primary query metadata
- **WHEN** `resource-history` or `hold-history` receives `spool_download_url` and `total_row_count` in the `POST /query` response
- **THEN** the page SHALL be allowed to initialize local DuckDB-WASM mode without waiting for a later `/view` response
- **THEN** the initial query response SHALL still remain usable if local activation is skipped or fails

#### Scenario: Parquet download failure fallback
- **WHEN** the Parquet download fails (network error, 410 expired, timeout)
- **THEN** the frontend SHALL fall back to server-side `/view` API for all view operations
- **THEN** a warning SHALL be logged to the console

### Requirement: Frontend SHALL execute view sub-queries locally when DuckDB-WASM is available
When a Parquet dataset is loaded in DuckDB-WASM, the frontend SHALL compute all page-specific view sub-queries locally.

#### Scenario: Local summary computation for Yield Alert and Reject History
- **WHEN** the user is on a `yield-alert` or `reject-history` page with DuckDB-WASM active
- **THEN** the page SHALL compute its summary and detail sub-queries via local SQL
- **THEN** results SHALL match server-computed values within banker's rounding tolerance

#### Scenario: Local view computation for Resource History
- **WHEN** the user is on the `resource-history` page with DuckDB-WASM active
- **THEN** KPI, trend, heatmap, workcenter comparison, and hierarchical detail views SHALL be computed locally from the Parquet spool
- **THEN** supplementary filter, sort, and pagination interactions SHALL be served without calling `GET /api/resource/history/view`

#### Scenario: Local view computation for Hold History
- **WHEN** the user is on the `hold-history` page with DuckDB-WASM active
- **THEN** trend, reason pareto, duration distribution, and paginated list views SHALL be computed locally from the Parquet spool
- **THEN** supplementary filter and pagination interactions SHALL be served without calling `GET /api/hold-history/view`

#### Scenario: Local filter/sort/page operations
- **WHEN** the user changes a supplementary filter, sort order, or page number while DuckDB-WASM mode is active
- **THEN** the operation SHALL be executed against the local DuckDB-WASM table
- **THEN** no server `/view` API request SHALL be made for that interaction

### Requirement: Frontend SHALL use a data-size threshold to choose between JSON and Parquet modes
The frontend SHALL automatically select the appropriate data processing mode based on the dataset size reported by the server.

#### Scenario: Small dataset uses JSON mode
- **WHEN** the server response indicates total row count less than or equal to the configured local-compute threshold
- **THEN** the frontend SHALL use the JSON payload and existing page state directly
- **THEN** DuckDB-WASM activation SHALL be skipped

#### Scenario: Large dataset uses Parquet mode
- **WHEN** the server response indicates total row count greater than the configured local-compute threshold and provides `spool_download_url`
- **THEN** the frontend SHALL prefer DuckDB-WASM activation
- **THEN** all subsequent eligible view operations SHALL use local SQL queries

#### Scenario: Eligibility metadata is absent
- **WHEN** a page response does not include `spool_download_url`
- **THEN** the frontend SHALL remain in server-compute mode
- **THEN** existing `/view` request behavior SHALL remain unchanged

### Requirement: Frontend SHALL fall back to server-side view when DuckDB-WASM is unavailable
The frontend SHALL detect browser capability and fall back gracefully when DuckDB-WASM cannot be used.

#### Scenario: Browser lacks required runtime support
- **WHEN** the browser does not support the required Worker or WebAssembly capabilities
- **THEN** the frontend SHALL skip DuckDB-WASM initialization entirely
- **THEN** all view operations SHALL use the existing server-side `/view` API

#### Scenario: Client-side activation is disabled or constrained
- **WHEN** the page-level feature flag is disabled or the dataset exceeds configured client safety limits
- **THEN** the frontend SHALL skip local mode and continue using the server-side `/view` API
- **THEN** the primary query response SHALL still be rendered normally

#### Scenario: Spool expires after the page has stored query state
- **WHEN** the spool download or local refresh path fails because the spool has expired
- **THEN** the frontend SHALL tear down local mode
- **THEN** the page SHALL resume server-side behavior or re-run the primary query using the last committed filters

### Requirement: Risk score and risk level SHALL be computable on the frontend
The yield-alert risk scoring formula SHALL be available as a frontend function for client-side computation.

#### Scenario: Frontend risk score calculation
- **WHEN** a yield-alert detail row has yield_pct and scrap_qty values
- **THEN** risk_score SHALL be computed as `max(0, (threshold - yield_pct) + min(scrap_qty, 200) / 20.0)`
- **THEN** risk_level SHALL be assigned as:
  - `high` when `yield_pct < threshold - 2.0 OR scrap_qty >= 100`
  - `medium` when `yield_pct < threshold OR scrap_qty >= 20`
  - `low` otherwise
- **THEN** the threshold value SHALL be provided by the server in the initial query response
