## MODIFIED Requirements

### Requirement: Hold dataset cache SHALL execute a single Oracle query and cache the result
The hold_dataset_cache module SHALL query Oracle via chunked batch queries and cache the result to Parquet spool for subsequent DuckDB-based derivations.

#### Scenario: Primary query execution and caching
- **WHEN** `execute_primary_query()` is called with date range and hold_type parameters
- **THEN** a deterministic `query_id` SHALL be computed from the primary params (start_date, end_date) using SHA256
- **THEN** if a cached spool file exists for this query_id, it SHALL be used without querying Oracle
- **THEN** if no cache exists, chunked Oracle queries SHALL fetch hold/release records via `decompose_by_time_range()` + `execute_plan()`
- **THEN** chunks SHALL be stream-merged to a Parquet spool file via `merge_chunks_to_spool()`
- **THEN** the spool metadata SHALL be registered in Redis with query_id, row_count, and TTL
- **THEN** the response SHALL include `query_id`, trend, reason_pareto, duration, and list page 1

#### Scenario: Cache TTL and eviction
- **WHEN** a spool file is created
- **THEN** the spool TTL SHALL be 900 seconds (15 minutes)
- **THEN** the Redis namespace SHALL be `hold_dataset`

### Requirement: Hold dataset cache SHALL derive trend data from cached DataFrame
The module SHALL compute daily trend aggregations from the cached fact set via DuckDB SQL runtime.

#### Scenario: Trend derivation via DuckDB
- **WHEN** `apply_view()` is called with a valid query_id
- **THEN** DuckDB SHALL derive trend data by grouping the spool Parquet by date using SQL aggregation
- **THEN** the 07:30 shift boundary rule SHALL be applied
- **THEN** all three hold_type variants (quality, non_quality, all) SHALL be computed from SQL WHERE clauses
- **THEN** hold_type filtering SHALL be applied via SQL, not in-memory Pandas

### Requirement: Hold dataset cache SHALL derive reason Pareto from cached DataFrame
The module SHALL compute reason distribution from the cached fact set via DuckDB SQL runtime.

#### Scenario: Reason Pareto derivation via DuckDB
- **WHEN** `apply_view()` is called with hold_type filter
- **THEN** DuckDB SHALL derive reason Pareto by grouping the filtered data by HOLDREASONNAME
- **THEN** items SHALL include count, qty, pct, and cumPct
- **THEN** items SHALL be sorted by count descending

### Requirement: Hold dataset cache SHALL derive duration distribution from cached DataFrame
The module SHALL compute hold duration buckets from the cached fact set via DuckDB SQL runtime.

#### Scenario: Duration derivation via DuckDB
- **WHEN** `apply_view()` is called with hold_type filter
- **THEN** DuckDB SHALL derive duration distribution from records where RELEASETXNDATE IS NOT NULL
- **THEN** 4 buckets SHALL be computed via SQL CASE expressions: <4h, 4-24h, 1-3d, >3d
- **THEN** each bucket SHALL include count and pct

### Requirement: Hold dataset cache SHALL derive paginated list from cached DataFrame
The module SHALL provide paginated detail records from the cached fact set via DuckDB SQL runtime.

#### Scenario: List pagination via DuckDB
- **WHEN** `apply_view()` is called with page and per_page parameters
- **THEN** DuckDB SHALL filter the spool Parquet by hold_type and optional reason filter
- **THEN** records SHALL be sorted by HOLDTXNDATE descending via SQL ORDER BY
- **THEN** pagination SHALL be applied via SQL LIMIT/OFFSET
- **THEN** response SHALL include items and pagination metadata (page, perPage, total, totalPages)

### Requirement: Hold dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired.

#### Scenario: Cache expired during view request
- **WHEN** `apply_view()` is called with a query_id whose spool file has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)
