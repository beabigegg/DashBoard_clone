## MODIFIED Requirements

### Requirement: Resource dataset cache SHALL execute a single Oracle query and cache the result
The resource_dataset_cache module SHALL query Oracle via chunked batch queries for both shift-status data AND OEE production/NG data, caching both to Parquet spool for subsequent DuckDB-based derivations.

#### Scenario: Primary query execution and caching
- **WHEN** `execute_primary_query()` is called with date range, granularity, and resource filter parameters
- **THEN** a `query_id` SHALL be computed (the primary path currently includes all params; a separate canonical query_id from date_range + granularity only is used by the warmup/reuse path via `try_compute_query_from_canonical_spool`)
- **THEN** if a cached spool file exists for this query_id, it SHALL be used without querying Oracle
- **THEN** if no cache exists, TWO Oracle queries SHALL execute in parallel:
  1. `base_facts.sql` — shift-status records from `DW_MES_RESOURCESTATUS_SHIFT`
  2. `oee_facts.sql` — production trackout + NG records from `DW_MES_LOTWIPHISTORY` + `DW_MES_LOTREJECTHISTORY` (全部設備，不含 filter)
- **THEN** for long date ranges, both queries SHALL use `batch_query_engine` (time-range decomposition → chunk merge → spool)
- **THEN** each query's results SHALL be written to separate Parquet spool files (prefix `resource` and `resource_oee`)
- **THEN** filter params (workcenter/family/resource/flags) SHALL be applied at DuckDB view-time, not baked into spool
- **THEN** `apply_view()` SHALL call DuckDB runtime as the sole compute path; on failure it returns None → route returns 410 cache_expired
- **THEN** the response SHALL include `query_id`, summary (KPI with OEE, trend with OEE, heatmap, comparison), and detail page 1

### Requirement: Resource dataset cache SHALL derive KPI summary from cached DataFrame
The module SHALL compute aggregated KPI metrics including OEE from the cached fact sets via DuckDB SQL runtime.

#### Scenario: KPI derivation via DuckDB (sole compute path)
- **WHEN** summary view is derived from the spool Parquet files
- **THEN** DuckDB SHALL apply resource filter params (workcenter/family/resource/flags) at query time via WHERE clauses on the spool views
- **THEN** DuckDB SHALL compute total hours for PRD, SBY, UDT, SDT, EGT, NST from the base facts spool
- **THEN** DuckDB SHALL compute total TRACKOUT_QTY and NG_QTY from the OEE facts spool
- **THEN** OU%, AVAIL%, yield_pct, and oee_pct SHALL be computed from the aggregated values
- **THEN** the KPI response SHALL include `oee_pct`, `yield_pct`, `trackout_qty`, and `ng_qty` fields

### Requirement: Resource dataset cache SHALL derive trend data from cached DataFrame
The module SHALL compute time-series aggregations including OEE from the cached fact sets via DuckDB SQL runtime.

#### Scenario: Trend derivation via DuckDB
- **WHEN** summary view is derived with a given granularity (day/week/month/year)
- **THEN** DuckDB SHALL JOIN base facts and OEE facts by `HISTORYID = EQUIPMENTID` and `DATA_DATE = SHIFT_DATE`
- **THEN** each period SHALL include existing hour metrics plus `oee_pct`, `yield_pct`
- **THEN** periods with no OEE data SHALL show `oee_pct: null` and `yield_pct: null`

### Requirement: Resource dataset cache SHALL derive heatmap from cached DataFrame
The module SHALL compute workcenter x date metric matrix supporting OEE from the cached fact sets via DuckDB SQL runtime.

#### Scenario: Heatmap derivation via DuckDB
- **WHEN** summary view is derived
- **THEN** DuckDB SHALL compute OU%, OEE%, and AVAIL% per workcenter per date
- **THEN** OEE% SHALL be computed by JOINing OEE facts to base facts per workcenter
- **THEN** all three metrics SHALL be included in each heatmap cell for frontend metric toggle

### Requirement: Resource dataset cache SHALL derive paginated detail from cached DataFrame
The module SHALL provide hierarchical detail records including OEE from the cached fact sets via DuckDB SQL runtime.

#### Scenario: Detail derivation with OEE via DuckDB
- **WHEN** detail view is requested
- **THEN** DuckDB SHALL LEFT JOIN OEE facts to base facts by `HISTORYID = EQUIPMENTID`
- **THEN** each resource row SHALL include `oee_pct`, `yield_pct`, `trackout_qty`, `ng_qty`
- **THEN** resources with no OEE data SHALL show null for OEE fields
