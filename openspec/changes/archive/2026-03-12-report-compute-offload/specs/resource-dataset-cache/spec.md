## MODIFIED Requirements

### Requirement: Resource dataset cache SHALL execute a single Oracle query and cache the result
The resource_dataset_cache module SHALL query Oracle via chunked batch queries and cache the result to Parquet spool for subsequent DuckDB-based derivations.

#### Scenario: Primary query execution and caching
- **WHEN** `execute_primary_query()` is called with date range, granularity, and resource filter parameters
- **THEN** a deterministic `query_id` SHALL be computed from all primary params using SHA256
- **THEN** if a cached spool file exists for this query_id, it SHALL be used without querying Oracle
- **THEN** if no cache exists, chunked Oracle queries SHALL fetch shift-status records via `decompose_by_time_range()` + `execute_plan()`
- **THEN** chunks SHALL be stream-merged to a Parquet spool file via `merge_chunks_to_spool()`
- **THEN** the spool metadata SHALL be registered in Redis with query_id, row_count, and TTL
- **THEN** the response SHALL include `query_id`, summary (KPI, trend, heatmap, comparison), and detail page 1

#### Scenario: Cache TTL and eviction
- **WHEN** a spool file is created
- **THEN** the spool TTL SHALL be 900 seconds (15 minutes)
- **THEN** the Redis namespace SHALL be `resource_dataset`

### Requirement: Resource dataset cache SHALL derive KPI summary from cached DataFrame
The module SHALL compute aggregated KPI metrics from the cached fact set via DuckDB SQL runtime.

#### Scenario: KPI derivation via DuckDB
- **WHEN** summary view is derived from the spool Parquet file
- **THEN** DuckDB SHALL compute total hours for PRD, SBY, UDT, SDT, EGT, NST via SQL aggregation
- **THEN** OU% and AVAIL% SHALL be computed from the hour totals
- **THEN** machine count SHALL be the COUNT DISTINCT of HISTORYID
- **THEN** no Pandas DataFrame SHALL be created during this derivation

### Requirement: Resource dataset cache SHALL derive trend data from cached DataFrame
The module SHALL compute time-series aggregations from the cached fact set via DuckDB SQL runtime.

#### Scenario: Trend derivation via DuckDB
- **WHEN** summary view is derived with a given granularity (day/week/month/year)
- **THEN** DuckDB SHALL group by the granularity period using SQL date functions
- **THEN** each period SHALL include PRD, SBY, UDT, SDT, EGT, NST hours and computed OU%, AVAIL%
- **THEN** no Pandas DataFrame SHALL be created during this derivation

### Requirement: Resource dataset cache SHALL derive heatmap from cached DataFrame
The module SHALL compute workcenter x date OU% matrix from the cached fact set via DuckDB SQL runtime.

#### Scenario: Heatmap derivation via DuckDB
- **WHEN** summary view is derived
- **THEN** DuckDB SHALL group by (workcenter, date) using SQL aggregation
- **THEN** each cell SHALL contain the OU% for that workcenter on that date
- **THEN** workcenters SHALL be sorted by workcenter_seq

### Requirement: Resource dataset cache SHALL derive workcenter comparison from cached DataFrame
The module SHALL compute per-workcenter aggregated metrics from the cached fact set via DuckDB SQL runtime.

#### Scenario: Comparison derivation via DuckDB
- **WHEN** summary view is derived
- **THEN** DuckDB SHALL group by workcenter using SQL aggregation
- **THEN** each workcenter SHALL include total hours and computed OU%
- **THEN** results SHALL be sorted by OU% descending, limited to top 15

### Requirement: Resource dataset cache SHALL derive paginated detail from cached DataFrame
The module SHALL provide hierarchical detail records from the cached fact set via DuckDB SQL runtime.

#### Scenario: Detail derivation and pagination via DuckDB
- **WHEN** detail view is requested with page and per_page parameters
- **THEN** DuckDB SHALL compute per-resource metrics from the spool Parquet file
- **THEN** resource dimension data (WORKCENTERNAME, RESOURCEFAMILYNAME) SHALL be merged from resource_cache
- **THEN** results SHALL be structured as a hierarchical tree (workcenter -> family -> resource)
- **THEN** pagination SHALL be applied via SQL LIMIT/OFFSET

### Requirement: Resource dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired.

#### Scenario: Cache expired during view request
- **WHEN** a view is requested with a query_id whose spool file has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)
