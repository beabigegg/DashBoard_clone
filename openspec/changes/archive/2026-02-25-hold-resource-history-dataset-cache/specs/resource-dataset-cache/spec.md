## ADDED Requirements

### Requirement: Resource dataset cache SHALL execute a single Oracle query and cache the result
The resource_dataset_cache module SHALL query Oracle once for the full shift-status fact set and cache it for subsequent derivations.

#### Scenario: Primary query execution and caching
- **WHEN** `execute_primary_query()` is called with date range, granularity, and resource filter parameters
- **THEN** a deterministic `query_id` SHALL be computed from all primary params using SHA256
- **THEN** if a cached DataFrame exists for this query_id (L1 or L2), it SHALL be used without querying Oracle
- **THEN** if no cache exists, a single Oracle query SHALL fetch all shift-status records from `DW_MES_RESOURCESTATUS_SHIFT` for the filtered resources and date range
- **THEN** the result DataFrame SHALL be stored in both L1 (ProcessLevelCache) and L2 (Redis as parquet/base64)
- **THEN** the response SHALL include `query_id`, summary (KPI, trend, heatmap, comparison), and detail page 1

#### Scenario: Cache TTL and eviction
- **WHEN** a DataFrame is cached
- **THEN** the cache TTL SHALL be 900 seconds (15 minutes)
- **THEN** L1 cache max_size SHALL be 8 entries with LRU eviction
- **THEN** the Redis namespace SHALL be `resource_dataset`

### Requirement: Resource dataset cache SHALL derive KPI summary from cached DataFrame
The module SHALL compute aggregated KPI metrics from the cached fact set.

#### Scenario: KPI derivation from cache
- **WHEN** summary view is derived from cached DataFrame
- **THEN** total hours for PRD, SBY, UDT, SDT, EGT, NST SHALL be summed
- **THEN** OU% and AVAIL% SHALL be computed from the hour totals
- **THEN** machine count SHALL be the distinct count of HISTORYID in the cached data

### Requirement: Resource dataset cache SHALL derive trend data from cached DataFrame
The module SHALL compute time-series aggregations from the cached fact set.

#### Scenario: Trend derivation
- **WHEN** summary view is derived with a given granularity (day/week/month/year)
- **THEN** the cached DataFrame SHALL be grouped by the granularity period
- **THEN** each period SHALL include PRD, SBY, UDT, SDT, EGT, NST hours and computed OU%, AVAIL%

### Requirement: Resource dataset cache SHALL derive heatmap from cached DataFrame
The module SHALL compute workcenter × date OU% matrix from the cached fact set.

#### Scenario: Heatmap derivation
- **WHEN** summary view is derived
- **THEN** the cached DataFrame SHALL be grouped by (workcenter, date)
- **THEN** each cell SHALL contain the OU% for that workcenter on that date
- **THEN** workcenters SHALL be sorted by workcenter_seq

### Requirement: Resource dataset cache SHALL derive workcenter comparison from cached DataFrame
The module SHALL compute per-workcenter aggregated metrics from the cached fact set.

#### Scenario: Comparison derivation
- **WHEN** summary view is derived
- **THEN** the cached DataFrame SHALL be grouped by workcenter
- **THEN** each workcenter SHALL include total hours and computed OU%
- **THEN** results SHALL be sorted by OU% descending, limited to top 15

### Requirement: Resource dataset cache SHALL derive paginated detail from cached DataFrame
The module SHALL provide hierarchical detail records from the cached fact set.

#### Scenario: Detail derivation and pagination
- **WHEN** detail view is requested with page and per_page parameters
- **THEN** the cached DataFrame SHALL be used to compute per-resource metrics
- **THEN** resource dimension data (WORKCENTERNAME, RESOURCEFAMILYNAME) SHALL be merged from resource_cache
- **THEN** results SHALL be structured as a hierarchical tree (workcenter → family → resource)
- **THEN** pagination SHALL apply to the flattened list

### Requirement: Resource dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired.

#### Scenario: Cache expired during view request
- **WHEN** a view is requested with a query_id whose cache has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)
