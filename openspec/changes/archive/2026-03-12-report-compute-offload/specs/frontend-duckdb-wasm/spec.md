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

#### Scenario: Parquet download and registration
- **WHEN** a view query response includes `spool_download_url` and the dataset exceeds the JSON threshold
- **THEN** the frontend SHALL download the Parquet file via fetch()
- **THEN** the Parquet file SHALL be registered in the DuckDB-WASM instance as a named table
- **THEN** subsequent filter/sort/page operations SHALL query this local table instead of calling the server /view API

#### Scenario: Parquet download failure fallback
- **WHEN** the Parquet download fails (network error, 410 expired, timeout)
- **THEN** the frontend SHALL fall back to server-side /view API for all view operations
- **THEN** a warning SHALL be logged to the console

### Requirement: Frontend SHALL execute view sub-queries locally when DuckDB-WASM is available
When a Parquet dataset is loaded in DuckDB-WASM, the frontend SHALL compute all view sub-queries (summary, trend, heatmap, station_summary, package_summary, alerts detail) locally.

#### Scenario: Local summary computation
- **WHEN** the user is on a yield-alert or reject-history page with DuckDB-WASM active
- **THEN** summary metrics (transaction_qty, scrap_qty, yield_pct) SHALL be computed via local SQL
- **THEN** results SHALL match server-computed values within banker's rounding tolerance

#### Scenario: Local filter/sort/page operations
- **WHEN** the user changes a filter, sort order, or page number
- **THEN** the operation SHALL be executed against the local DuckDB-WASM table
- **THEN** no /view API request SHALL be made to the server
- **THEN** response time SHALL be under 200ms for datasets up to 50,000 rows

### Requirement: Frontend SHALL use a data-size threshold to choose between JSON and Parquet modes
The frontend SHALL automatically select the appropriate data processing mode based on the dataset size reported by the server.

#### Scenario: Small dataset uses JSON mode
- **WHEN** the server response indicates total row count ≤ 5,000
- **THEN** the frontend SHALL use the full JSON payload directly
- **THEN** filter/sort/page operations SHALL use JS Array methods (no DuckDB-WASM needed)

#### Scenario: Large dataset uses Parquet mode
- **WHEN** the server response indicates total row count > 5,000 and provides `spool_download_url`
- **THEN** the frontend SHALL download the Parquet file and initialize DuckDB-WASM
- **THEN** all subsequent view operations SHALL use local SQL queries

### Requirement: Frontend SHALL fall back to server-side view when DuckDB-WASM is unavailable
The frontend SHALL detect browser capability and fall back gracefully when DuckDB-WASM cannot be used.

#### Scenario: Browser lacks SharedArrayBuffer support
- **WHEN** the browser does not support SharedArrayBuffer (required by DuckDB-WASM)
- **THEN** the frontend SHALL skip DuckDB-WASM initialization entirely
- **THEN** all view operations SHALL use the existing server-side /view API

#### Scenario: Mobile device memory constraint
- **WHEN** the Parquet file size exceeds 50MB
- **THEN** the frontend SHALL skip local loading and use server-side /view API
- **THEN** the threshold SHALL be configurable via application config

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
