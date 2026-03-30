## Purpose
Define stable requirements for the resource-dataset-cache module, which manages Oracle query execution, Parquet spool caching, and DuckDB-based view derivation for the resource-history domain.
## Requirements
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
- **THEN** `execute_primary_query()` SHALL NOT call `_derive_summary()`, `_derive_detail()`, or any `_derive_*()` pandas function
- **THEN** `execute_primary_query()` SHALL NOT call `_get_cached_df()` to load a full DataFrame from Redis

#### Scenario: Bootstrap render failure after spool creation
- **WHEN** `execute_primary_query()` completes its Oracle/spool stage but `apply_view()` cannot produce a valid result for the bootstrap response
- **THEN** the function SHALL return an explicit failure response
- **THEN** the function SHALL NOT return a synthetic empty summary/detail payload with HTTP 200 semantics

#### Scenario: Direct-path query result stored via spool (Phase 2)
- **WHEN** `execute_primary_query()` completes via the direct path (non-engine)
- **THEN** `_store_df()` SHALL call `store_spooled_df(_REDIS_NAMESPACE, query_id, df, ttl_seconds=_CACHE_TTL)`
- **THEN** `_store_df()` SHALL NOT call `redis_df_store.redis_store_df()` when `PHASE2_METADATA_ONLY=1`

#### Scenario: Cache TTL and eviction
- **WHEN** a spool file is created
- **THEN** the spool TTL SHALL be 900 seconds (15 minutes)
- **THEN** the Redis spool metadata namespace SHALL be `resource_dataset`
- **THEN** the Redis key `resource_dataset:{query_id}` (Parquet+base64 payload) SHALL NOT be written when `PHASE2_METADATA_ONLY=1`

### Requirement: Resource dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired or the view engine cannot compute a result.

The resource-history domain is classified as **Type A** per the `query-response-semantic-contract`. On HTTP 410, the client SHALL re-trigger `execute_primary_query()` synchronously.

#### Scenario: Cache expired during view request
- **WHEN** a view is requested with a query_id whose spool file has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)

#### Scenario: DuckDB runtime failure during view request
- **WHEN** `apply_view()` is called and the DuckDB SQL runtime returns no result (spool miss, runtime error, or feature flag disabled)
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)
- **THEN** the system SHALL NOT call `_get_cached_df()` or any `_derive_*()` pandas function

#### Scenario: Type A client re-triggers sync query on 410
- **WHEN** the resource-history view endpoint returns HTTP 410
- **THEN** the client SHALL call `execute_primary_query()` synchronously (no 202 / polling flow)
- **THEN** upon receiving a 200 response, the client SHALL load the view with the returned data
- **THEN** the view endpoint SHALL NOT dispatch any background job as a side-effect of the 410

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

### Requirement: Resource dimension data convenience accessors

`resource_dataset_cache` SHALL export `_get_resource_lookup()` and `_get_workcenter_mapping()` as parameter-less convenience functions that return dimension data needed by downstream consumers (`resource_history_sql_runtime`, `resource_history_routes`).

- `_get_resource_lookup()` SHALL return a `Dict[str, Dict[str, Any]]` mapping RESOURCEID to resource info by delegating to `resource_history_service._get_filtered_resources()` (no filters) + `_build_resource_lookup()`.
- `_get_workcenter_mapping()` SHALL re-export `filter_cache.get_workcenter_mapping()`.

#### Scenario: sql_runtime loads dimension data successfully
- **WHEN** `resource_history_sql_runtime` imports `_get_resource_lookup` and `_get_workcenter_mapping` from `resource_dataset_cache`
- **THEN** both imports resolve without `ImportError`
- **AND** `_get_resource_lookup()` returns a dict keyed by RESOURCEID
- **AND** `_get_workcenter_mapping()` returns a dict keyed by workcenter name

#### Scenario: routes inject resource metadata successfully
- **WHEN** `resource_history_routes._inject_resource_metadata()` calls `_get_resource_lookup()` and `_get_workcenter_mapping()`
- **THEN** both calls succeed and return populated dicts when resource cache is warm

#### Scenario: e2e tests can patch the accessors
- **WHEN** e2e tests use `@patch('mes_dashboard.services.resource_dataset_cache._get_resource_lookup')`
- **THEN** the patch target resolves correctly

