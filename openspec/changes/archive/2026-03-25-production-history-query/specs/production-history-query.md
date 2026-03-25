## Overview

獨立頁面「生產歷程查詢」以 `PJ_TYPE + TrackIn 日期區間` 為主軸，提供：
- 上方 Matrix（WorkCenter Group → Spec → Equipment，按月份計數）
- 下方明細 TABLE（預設 25 rows/page）
- Matrix 聯動篩選、分頁與全量 CSV 匯出

後端採用：Oracle 分段查詢 → Parquet spool → DuckDB 衍生視圖（page / matrix / export）。

## ADDED Requirements

### Requirement: Production History API SHALL validate query input and date semantics
`POST /api/production-history/query` SHALL validate required fields, bound query size, and use deterministic date-boundary semantics before any Oracle query starts.

#### Scenario: Required fields and date range validation
- **WHEN** `pj_types` is empty or `start_date` / `end_date` is missing
- **THEN** API SHALL return HTTP 400 validation error
- **AND** Oracle query SHALL NOT execute

#### Scenario: Maximum date range
- **WHEN** requested date span exceeds `PROD_HISTORY_MAX_DATE_RANGE_DAYS` (default 180)
- **THEN** API SHALL return HTTP 400 validation error

#### Scenario: End-date exclusive behavior
- **WHEN** user sends `start_date=2026-03-01`, `end_date=2026-03-31`
- **THEN** service SHALL query TrackIn with `>= 2026-03-01 00:00:00` and `< 2026-04-01 00:00:00`
- **AND** conversion SHALL use plant timezone (Asia/Taipei)

### Requirement: Production History API SHALL return a stable success contract
All production-history endpoints SHALL use unified success envelope `{ success: true, data: ... }`.

#### Scenario: Query endpoint success envelope
- **WHEN** `POST /api/production-history/query` succeeds
- **THEN** response SHALL be `{ success: true, data: { dataset_id, detail, matrix, filter_options } }`

#### Scenario: Page endpoint success envelope
- **WHEN** `POST /api/production-history/page` succeeds
- **THEN** response SHALL be `{ success: true, data: { rows, pagination } }`

#### Scenario: Matrix endpoint success envelope
- **WHEN** `POST /api/production-history/matrix` succeeds
- **THEN** response SHALL be `{ success: true, data: { tree, month_columns } }`

### Requirement: Production History API SHALL use dataset-backed view endpoints
`/page`, `/matrix`, `/export` SHALL read from registered spool dataset only and SHALL NOT re-query Oracle.

#### Scenario: Query creates dataset and returns first view
- **WHEN** `POST /query` succeeds
- **THEN** service SHALL build parquet spool and return `dataset_id`
- **AND** response SHALL include first-page detail and initial matrix summary

#### Scenario: View endpoints use cached dataset
- **WHEN** `/page`, `/matrix`, `/export` is called with valid `dataset_id`
- **THEN** service SHALL use DuckDB-over-spool path
- **AND** Oracle SHALL NOT be queried again

### Requirement: Production History API SHALL define dataset lifecycle and expiry semantics
Dataset lifetime SHALL be explicit and expiry SHALL be machine-detectable by clients.

#### Scenario: Dataset expiry behavior
- **WHEN** `dataset_id` is missing, removed, or expired by spool TTL
- **THEN** `/page`, `/matrix`, `/export` SHALL return HTTP 410 with error code `dataset_expired`
- **AND** response SHALL guide client to re-run `/query`

#### Scenario: Dataset metadata on query response
- **WHEN** `/query` succeeds
- **THEN** response meta SHALL include effective TTL seconds (or expiry timestamp) for UI countdown/requery hint

### Requirement: Production History API SHALL define matrix filter contract explicitly
`/page` and `/matrix` SHALL share the same optional filter schema.

#### Scenario: Shared matrix filter schema
- **WHEN** filter is provided
- **THEN** accepted fields SHALL be `workcenter_group`, `spec`, `equipment_id`
- **AND** omitted fields SHALL mean "not constrained"

#### Scenario: Matrix recomputation under filter
- **WHEN** `POST /matrix` is called with `dataset_id` and filter
- **THEN** matrix totals and month columns SHALL be recomputed on the filtered subset

### Requirement: Production History API SHALL define export filter encoding
`GET /export` SHALL support stable query-string filter encoding without nested JSON ambiguity.

#### Scenario: Export query parameters
- **WHEN** client calls `/export`
- **THEN** accepted query params SHALL include `dataset_id`, `workcenter_group`, `spec`, `equipment_id`
- **AND** semantics SHALL match `/page` filter behavior

#### Scenario: Export data parity
- **WHEN** same filter context is used on `/page` and `/export`
- **THEN** CSV rows SHALL be from the same filtered dataset scope (except pagination truncation)

### Requirement: Production History API SHALL provide overload-safe retryable errors
Heavy-query front-door rejection and memory-guard rejection SHALL be reported as retryable overload errors.

#### Scenario: Heavy-query slot rejected
- **WHEN** `/query` cannot acquire heavy-query slot
- **THEN** endpoint SHALL return HTTP 503 with `Retry-After`
- **AND** payload SHALL include stable machine code `heavy_query_overloaded`

#### Scenario: Memory guard rejection on view endpoints
- **WHEN** `/page` `/matrix` `/export` hits memory guard rejection
- **THEN** endpoint SHALL return HTTP 503 with retryable error code `memory_guard_rejected`

### Requirement: Production History query engine SHALL use chunked Oracle execution with slow path
Primary query SHALL execute by time chunks and use `read_sql_df_slow` to isolate long-running Oracle traffic.

#### Scenario: Chunk decomposition and execution
- **WHEN** `/query` starts
- **THEN** service SHALL call `decompose_by_time_range(..., PROD_HISTORY_ENGINE_GRAIN_DAYS)`
- **AND** execute chunks via `execute_plan` with `PROD_HISTORY_MAX_ROWS_PER_CHUNK` bound

#### Scenario: Slow-path Oracle access
- **WHEN** chunk SQL executes
- **THEN** service SHALL use `read_sql_df_slow` instead of normal pooled fast path

### Requirement: Production History LOT trace SHALL be bounded and cycle-safe
LOT split-chain trace SHALL avoid infinite recursion and unstable runtime.

#### Scenario: Trace bounded by depth and dedup
- **WHEN** `lot_ids` is provided
- **THEN** service SHALL trace parent lots with max-depth bound and visited dedup
- **AND** trace result SHALL merge unique lot IDs only

#### Scenario: Trace overflow handling
- **WHEN** trace depth bound is exceeded or cycle detected
- **THEN** endpoint SHALL return HTTP 400 with descriptive validation error

### Requirement: Production History frontend SHALL provide matrix-detail linked interaction
`/production-history` page SHALL expose required filters, matrix selection, paginated detail, and export action.

#### Scenario: Required filter UX
- **WHEN** user has not entered required Type/date conditions
- **THEN** query action SHALL be blocked with inline validation feedback

#### Scenario: Matrix-to-detail linkage
- **WHEN** user selects matrix node at any level (group/spec/equipment)
- **THEN** frontend SHALL call `/page` with matching filter and update detail rows

#### Scenario: Route and shell registration
- **WHEN** app loads route contracts and native module registry
- **THEN** `/production-history` SHALL be available as native page entry and sidebar item
