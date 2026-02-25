## ADDED Requirements

### Requirement: Hold dataset cache SHALL execute a single Oracle query and cache the result
The hold_dataset_cache module SHALL query Oracle once for the full hold/release fact set and cache it for subsequent derivations.

#### Scenario: Primary query execution and caching
- **WHEN** `execute_primary_query()` is called with date range and hold_type parameters
- **THEN** a deterministic `query_id` SHALL be computed from the primary params (start_date, end_date) using SHA256
- **THEN** if a cached DataFrame exists for this query_id (L1 or L2), it SHALL be used without querying Oracle
- **THEN** if no cache exists, a single Oracle query SHALL fetch all hold/release records from `DW_MES_HOLDRELEASEHISTORY` for the date range (all hold_types)
- **THEN** the result DataFrame SHALL be stored in both L1 (ProcessLevelCache) and L2 (Redis as parquet/base64)
- **THEN** the response SHALL include `query_id`, trend, reason_pareto, duration, and list page 1

#### Scenario: Cache TTL and eviction
- **WHEN** a DataFrame is cached
- **THEN** the cache TTL SHALL be 900 seconds (15 minutes)
- **THEN** L1 cache max_size SHALL be 8 entries with LRU eviction
- **THEN** the Redis namespace SHALL be `hold_dataset`

### Requirement: Hold dataset cache SHALL derive trend data from cached DataFrame
The module SHALL compute daily trend aggregations from the cached fact set.

#### Scenario: Trend derivation from cache
- **WHEN** `apply_view()` is called with a valid query_id
- **THEN** trend data SHALL be derived by grouping the cached DataFrame by date
- **THEN** the 07:30 shift boundary rule SHALL be applied
- **THEN** all three hold_type variants (quality, non_quality, all) SHALL be computed from the same DataFrame
- **THEN** hold_type filtering SHALL be applied in-memory without re-querying Oracle

### Requirement: Hold dataset cache SHALL derive reason Pareto from cached DataFrame
The module SHALL compute reason distribution from the cached fact set.

#### Scenario: Reason Pareto derivation
- **WHEN** `apply_view()` is called with hold_type filter
- **THEN** reason Pareto SHALL be derived by grouping the filtered DataFrame by HOLDREASONNAME
- **THEN** items SHALL include count, qty, pct, and cumPct
- **THEN** items SHALL be sorted by count descending

### Requirement: Hold dataset cache SHALL derive duration distribution from cached DataFrame
The module SHALL compute hold duration buckets from the cached fact set.

#### Scenario: Duration derivation
- **WHEN** `apply_view()` is called with hold_type filter
- **THEN** duration distribution SHALL be derived from records where RELEASETXNDATE IS NOT NULL
- **THEN** 4 buckets SHALL be computed: <4h, 4-24h, 1-3d, >3d
- **THEN** each bucket SHALL include count and pct

### Requirement: Hold dataset cache SHALL derive paginated list from cached DataFrame
The module SHALL provide paginated detail records from the cached fact set.

#### Scenario: List pagination from cache
- **WHEN** `apply_view()` is called with page and per_page parameters
- **THEN** the cached DataFrame SHALL be filtered by hold_type and optional reason filter
- **THEN** records SHALL be sorted by HOLDTXNDATE descending
- **THEN** pagination SHALL be applied in-memory (offset + limit on the sorted DataFrame)
- **THEN** response SHALL include items and pagination metadata (page, perPage, total, totalPages)

### Requirement: Hold dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired.

#### Scenario: Cache expired during view request
- **WHEN** `apply_view()` is called with a query_id whose cache has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)
