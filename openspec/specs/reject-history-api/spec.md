# reject-history-api Specification

## Purpose
TBD - created by archiving change reject-history-query-page. Update Purpose after archive.
## Requirements
### Requirement: Reject History API SHALL validate required query parameters
The API SHALL validate date parameters and basic paging bounds before executing database work.

#### Scenario: Missing required dates
- **WHEN** a reject-history endpoint requiring date range is called without `start_date` or `end_date`
- **THEN** the API SHALL return HTTP 400 with a descriptive validation error

#### Scenario: Invalid date order
- **WHEN** `end_date` is earlier than `start_date`
- **THEN** the API SHALL return HTTP 400 and SHALL NOT run SQL queries

### Requirement: Reject History API SHALL provide summary metrics endpoint
The API SHALL provide aggregated summary metrics for the selected filter context.

#### Scenario: Summary response payload
- **WHEN** `GET /api/reject-history/summary` is called with valid filters
- **THEN** response SHALL be `{ success: true, data: { ... } }`
- **THEN** data SHALL include `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, `REJECT_RATE_PCT`, `DEFECT_RATE_PCT`, `REJECT_SHARE_PCT`, `AFFECTED_LOT_COUNT`, and `AFFECTED_WORKORDER_COUNT`

### Requirement: Reject History API SHALL support yield-exclusion policy toggle
The API SHALL support excluding or including policy-marked scrap reasons through a shared query parameter.

#### Scenario: Default policy mode
- **WHEN** reject-history endpoints are called without `include_excluded_scrap`
- **THEN** `include_excluded_scrap` SHALL default to `false`
- **THEN** rows mapped to `ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE.ENABLE_FLAG='Y'` SHALL be excluded from yield-related calculations

#### Scenario: Explicitly include policy-marked scrap
- **WHEN** `include_excluded_scrap=true` is provided
- **THEN** policy-marked rows SHALL be included in summary/trend/pareto/list/export calculations
- **THEN** API response `meta` SHALL include the effective `include_excluded_scrap` value

#### Scenario: Invalid toggle value
- **WHEN** `include_excluded_scrap` is not parseable as boolean
- **THEN** the API SHALL return HTTP 400 with a descriptive validation error

### Requirement: Reject History API SHALL provide trend endpoint
The API SHALL return time-series trend data for quantity and rate metrics.

#### Scenario: Trend response structure
- **WHEN** `GET /api/reject-history/trend` is called
- **THEN** response SHALL be `{ success: true, data: { items: [...] } }`
- **THEN** each trend item SHALL contain bucket date, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, `REJECT_RATE_PCT`, and `DEFECT_RATE_PCT`

#### Scenario: Trend granularity
- **WHEN** `granularity` is provided as `day`, `week`, or `month`
- **THEN** the API SHALL aggregate by the requested granularity
- **THEN** invalid granularity SHALL return HTTP 400

### Requirement: Reject History API SHALL provide reason Pareto endpoint
The API SHALL return sorted reason distribution data with cumulative percentages.

#### Scenario: Pareto response payload
- **WHEN** `GET /api/reject-history/reason-pareto` is called
- **THEN** each item SHALL include `reason`, `category`, selected metric value, `pct`, and `cumPct`
- **THEN** items SHALL be sorted descending by selected metric

#### Scenario: Metric mode validation
- **WHEN** `metric_mode` is provided
- **THEN** accepted values SHALL be `reject_total` or `defect`
- **THEN** invalid `metric_mode` SHALL return HTTP 400

### Requirement: Reject History API SHALL provide paginated detail endpoint
The API SHALL return paginated detailed rows for the selected filter context.

#### Scenario: List response payload
- **WHEN** `GET /api/reject-history/list?page=1&per_page=50` is called
- **THEN** response SHALL include `{ items: [...], pagination: { page, perPage, total, totalPages } }`
- **THEN** each row SHALL include date, process dimensions, reason fields, `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, and reject component columns

#### Scenario: Paging bounds
- **WHEN** `page < 1`
- **THEN** page SHALL be treated as 1
- **WHEN** `per_page > 200`
- **THEN** `per_page` SHALL be capped at 200

### Requirement: Reject History API SHALL provide CSV export endpoint
The API SHALL provide CSV export using the same filter and metric semantics as list/query APIs.

#### Scenario: Export payload consistency
- **WHEN** `GET /api/reject-history/export` is called with valid filters
- **THEN** CSV headers SHALL include both `REJECT_TOTAL_QTY` and `DEFECT_QTY`
- **THEN** export rows SHALL follow the same semantic definitions as summary/list endpoints

#### Scenario: Cached export supports full detail-filter parity
- **WHEN** `GET /api/reject-history/export-cached` is called with an existing `query_id`
- **THEN** the endpoint SHALL apply primary policy toggles, supplementary filters, trend-date filters, metric filter, and Pareto-selected item filters
- **THEN** returned rows SHALL match the same filtered detail dataset semantics used by `GET /api/reject-history/view`

#### Scenario: CSV encoding and escaping are stable
- **WHEN** either export endpoint returns CSV
- **THEN** response charset SHALL be `utf-8-sig`
- **THEN** values containing commas, quotes, or newlines SHALL be CSV-escaped correctly

### Requirement: Reject History API SHALL centralize SQL in reject_history SQL directory
The service SHALL load SQL from dedicated files under `src/mes_dashboard/sql/reject_history/`.

#### Scenario: SQL file loading
- **WHEN** reject-history service executes queries
- **THEN** SQL SHALL be loaded from files in `sql/reject_history`
- **THEN** user-supplied filters SHALL be passed through bind parameters
- **THEN** user input SHALL NOT be interpolated into SQL strings directly

### Requirement: Reject History API SHALL use cached exclusion-policy source
The API SHALL read exclusion-policy reasons from cached `ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE` data instead of querying Oracle on every request.

#### Scenario: Enabled exclusions only
- **WHEN** exclusion-policy data is loaded
- **THEN** only rows with `ENABLE_FLAG='Y'` SHALL be treated as active exclusions

#### Scenario: Daily full-table cache refresh
- **WHEN** exclusion cache is initialized
- **THEN** the full table SHALL be loaded and refreshed at least once per 24 hours
- **THEN** Redis SHOULD be used as shared cache when available, with in-memory fallback when unavailable

### Requirement: Reject History API SHALL apply rate limiting on expensive endpoints
The API SHALL rate-limit high-cost endpoints to protect Oracle and application resources.

#### Scenario: List and export rate limiting
- **WHEN** `/api/reject-history/list` or `/api/reject-history/export` receives excessive requests
- **THEN** configured rate limiting SHALL reject requests beyond the threshold within the time window

### Requirement: Database query execution path
The reject-history service (`reject_history_service.py` and `reject_dataset_cache.py`) SHALL use `read_sql_df_slow` (dedicated connection) instead of `read_sql_df` (pooled connection) for all Oracle queries.

#### Scenario: Primary query uses dedicated connection
- **WHEN** the reject-history primary query is executed
- **THEN** it uses `read_sql_df_slow` which creates a dedicated Oracle connection outside the pool
- **AND** the connection has a 300-second call_timeout (configurable)
- **AND** the connection is subject to the global slow query semaphore

