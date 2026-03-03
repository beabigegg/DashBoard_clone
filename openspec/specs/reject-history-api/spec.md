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

#### Scenario: Date range exceeds maximum
- **WHEN** the date range between `start_date` and `end_date` exceeds 730 days
- **THEN** the API SHALL return HTTP 400 with error message "日期範圍不可超過 730 天"

### Requirement: Reject History API primary query response SHALL include partial failure metadata
The primary query endpoint SHALL include batch execution completeness information in the response `meta` field when chunks fail during batch query execution.

#### Scenario: Partial failure metadata in response
- **WHEN** `POST /api/reject-history/query` completes with some chunks failing
- **THEN** the response SHALL include `meta.has_partial_failure: true`
- **THEN** the response SHALL include `meta.failed_chunk_count` as a positive integer
- **THEN** the response SHALL include `meta.failed_ranges` as an array of `{start, end}` date strings (if available)
- **THEN** the HTTP status SHALL still be 200 (data is partially available)

#### Scenario: No partial failure metadata on full success
- **WHEN** `POST /api/reject-history/query` completes with all chunks succeeding
- **THEN** the response `meta` SHALL NOT include `has_partial_failure`, `failed_chunk_count`, or `failed_ranges`

#### Scenario: Partial failure metadata preserved on cache hit
- **WHEN** `POST /api/reject-history/query` returns cached data that originally had partial failures
- **THEN** the response SHALL include the same `meta.has_partial_failure`, `meta.failed_chunk_count`, and `meta.failed_ranges` as the original response

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
The API SHALL return sorted reason distribution data with cumulative percentages. The endpoint supports dimension selection via `dimension` parameter for single-dimension queries.

#### Scenario: Pareto response payload
- **WHEN** `GET /api/reject-history/reason-pareto` is called
- **THEN** each item SHALL include `reason`, `category`, selected metric value, `pct`, and `cumPct`
- **THEN** items SHALL be sorted descending by selected metric

#### Scenario: Metric mode validation
- **WHEN** `metric_mode` is provided
- **THEN** accepted values SHALL be `reject_total` or `defect`
- **THEN** invalid `metric_mode` SHALL return HTTP 400

#### Scenario: Dimension selection
- **WHEN** `dimension` parameter is provided with a valid value (reason, package, type, workflow, workcenter, equipment)
- **THEN** the endpoint SHALL return Pareto data for that dimension
- **WHEN** `dimension` is not provided
- **THEN** the endpoint SHALL default to `reason`

### Requirement: Reject History API SHALL provide batch Pareto endpoint with cross-filter
The API SHALL provide a batch Pareto endpoint that returns all 6 dimension Pareto results in a single response, supporting cross-dimension filtering with exclude-self logic.

#### Scenario: Batch Pareto response structure
- **WHEN** `GET /api/reject-history/batch-pareto` is called with valid `query_id`
- **THEN** response SHALL be `{ success: true, data: { dimensions: { reason: {...}, package: {...}, type: {...}, workflow: {...}, workcenter: {...}, equipment: {...} } } }`
- **THEN** each dimension object SHALL include `items` array with same schema as reason-pareto items (`reason`, `metric_value`, `pct`, `cumPct`, `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, `count`)

#### Scenario: Cross-filter exclude-self logic
- **WHEN** `sel_reason=A&sel_type=X` is provided
- **THEN** reason Pareto SHALL be computed with type=X filter applied (but NOT reason=A filter)
- **THEN** type Pareto SHALL be computed with reason=A filter applied (but NOT type=X filter)
- **THEN** package/workflow/workcenter/equipment Paretos SHALL be computed with both reason=A AND type=X filters applied

#### Scenario: Empty selections return unfiltered Paretos
- **WHEN** batch-pareto is called with no `sel_*` parameters
- **THEN** all 6 dimensions SHALL return their full Pareto distribution (same as calling reason-pareto individually with no cross-filter)

#### Scenario: Cache-only computation
- **WHEN** `query_id` does not exist in cache
- **THEN** the endpoint SHALL return HTTP 400 with error message indicating cache miss
- **THEN** the endpoint SHALL NOT fall back to Oracle query

#### Scenario: Supplementary and policy filters apply
- **WHEN** batch-pareto is called with supplementary filters (packages, workcenter_groups, reason) and policy toggles
- **THEN** all 6 dimension Paretos SHALL be computed after applying policy and supplementary filters first (before cross-filter)

#### Scenario: Data source is cached DataFrame only
- **WHEN** batch-pareto computes dimension Paretos
- **THEN** computation SHALL operate on the in-memory cached Pandas DataFrame (populated by the primary query)
- **THEN** the endpoint SHALL NOT issue any additional Oracle database queries
- **THEN** response time SHALL be sub-100ms since all computation is in-memory

#### Scenario: Display scope (TOP20) support
- **WHEN** `pareto_display_scope=top20` is provided
- **THEN** applicable dimensions (type, workflow, equipment) SHALL truncate results to top 20 items after sorting
- **WHEN** `pareto_display_scope` is omitted or `all`
- **THEN** all items SHALL be returned (subject to pareto_scope 80% filter if active)

### Requirement: Reject History API SHALL support multi-dimension Pareto selection in view and export
The detail view and export endpoints SHALL accept multiple dimension selections simultaneously and apply them with AND logic.

#### Scenario: Multi-dimension filter on view endpoint
- **WHEN** `GET /api/reject-history/view` is called with `sel_reason=A&sel_type=X`
- **THEN** returned rows SHALL match reason=A AND type=X (both filters applied simultaneously)

#### Scenario: Multi-dimension filter on export endpoint
- **WHEN** `GET /api/reject-history/export-cached` is called with `sel_reason=A&sel_type=X`
- **THEN** exported CSV SHALL contain only rows matching reason=A AND type=X

#### Scenario: Backward compatibility with single-dimension params
- **WHEN** `pareto_dimension` and `pareto_values` are provided (legacy format)
- **THEN** the API SHALL still accept and apply them as before
- **WHEN** both `sel_*` params and legacy params are provided
- **THEN** `sel_*` params SHALL take precedence

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

