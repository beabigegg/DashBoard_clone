## ADDED Requirements

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

### Requirement: Reject History API SHALL centralize SQL in reject_history SQL directory
The service SHALL load SQL from dedicated files under `src/mes_dashboard/sql/reject_history/`.

#### Scenario: SQL file loading
- **WHEN** reject-history service executes queries
- **THEN** SQL SHALL be loaded from files in `sql/reject_history`
- **THEN** user-supplied filters SHALL be passed through bind parameters
- **THEN** user input SHALL NOT be interpolated into SQL strings directly

### Requirement: Reject History API SHALL apply rate limiting on expensive endpoints
The API SHALL rate-limit high-cost endpoints to protect Oracle and application resources.

#### Scenario: List and export rate limiting
- **WHEN** `/api/reject-history/list` or `/api/reject-history/export` receives excessive requests
- **THEN** configured rate limiting SHALL reject requests beyond the threshold within the time window
