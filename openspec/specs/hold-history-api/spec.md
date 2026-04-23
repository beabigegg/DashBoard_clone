## Purpose
Define stable requirements for hold-history-api.

## Requirements

### Requirement: Hold History API SHALL provide daily trend data with Redis caching
The Hold History API SHALL return trend, reason-pareto, duration, and list data from a single cached dataset via a two-phase query pattern (POST /query + GET /view). The trend payload SHALL include a stable "quality repeat hold" series derived from `(lot, reason)` re-hold history, independent of the `FUTUREHOLDCOMMENTS` column.

#### Scenario: Primary query endpoint
- **WHEN** `POST /api/hold-history/query` is called with `{ start_date, end_date, hold_type }`
- **THEN** the service SHALL execute a single Oracle query (or read from cache) via `hold_dataset_cache.execute_primary_query()`
- **THEN** the response SHALL return `{ success: true, data: { query_id, trend, reason_pareto, duration, list, summary } }`
- **THEN** list SHALL contain page 1 with default per_page of 50

#### Scenario: Supplementary view endpoint
- **WHEN** `GET /api/hold-history/view?query_id=...&hold_type=...&reason=...&page=...&per_page=...` is called
- **THEN** the service SHALL read the cached DataFrame and derive filtered views via `hold_dataset_cache.apply_view()`
- **THEN** no Oracle query SHALL be executed
- **THEN** the response SHALL return `{ success: true, data: { trend, reason_pareto, duration, list } }`

#### Scenario: Cache expired on view request
- **WHEN** GET /view is called with an expired query_id
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }` with HTTP 410

#### Scenario: Trend uses shift boundary at 07:30
- **WHEN** daily aggregation is calculated
- **THEN** transactions with time >= 07:30 SHALL be attributed to the next calendar day
- **THEN** transactions with time < 07:30 SHALL be attributed to the current calendar day

#### Scenario: Trend hold type classification
- **WHEN** trend data is aggregated by hold type
- **THEN** quality classification SHALL use the same NON_QUALITY_HOLD_REASONS set as existing hold endpoints

#### Scenario: Quality repeat hold series in trend payload

- **WHEN** daily trend is computed for each day in the query range
- **THEN** each day SHALL include `repeatQualityHoldQty`: `SUM(QTY)` over rows where `hold_day = day AND RN_FUTURE_REASON > 1 AND hold_type = 'quality'`
- **AND** the computation SHALL NOT require `FUTUREHOLDCOMMENTS IS NOT NULL`
- **AND** the partition for `RN_FUTURE_REASON` SHALL use `(CONTAINERID, HOLDREASONID)` ordered by `HOLDTXNDATE` (same as existing `base_facts.sql`)
- **AND** the value SHALL be consistent across Oracle (`trend.sql`), DuckDB server (`hold_history_sql_runtime._query_trend`), and DuckDB WASM (`useHoldHistoryDuckDB.queryTrend`)
- **AND** the existing `newHoldQty` / `releaseQty` / `holdQty` / `futureHoldQty` calculations SHALL remain unchanged

### Requirement: Hold History API SHALL provide reason Pareto data
The reason Pareto data SHALL be derived from the cached dataset, not from a separate Oracle query.

#### Scenario: Reason Pareto from cache
- **WHEN** reason Pareto is requested via GET /view with hold_type filter
- **THEN** the cached DataFrame SHALL be filtered by hold_type and grouped by HOLDREASONNAME
- **THEN** each item SHALL contain `{ reason, count, qty, pct, cumPct }`
- **THEN** items SHALL be sorted by count descending

### Requirement: Hold History API SHALL provide hold duration distribution
The duration distribution SHALL be derived from the cached dataset, and the response SHALL include real-average and real-maximum hold-duration metrics alongside the bucket distribution.

#### Scenario: Duration from cache
- **WHEN** duration is requested via GET /view
- **THEN** the cached DataFrame SHALL be filtered to released holds only for bucket computation
- **THEN** 4 buckets SHALL be computed: <4h, 4-24h, 1-3d, >3d

#### Scenario: Real-average and real-maximum hold duration in duration payload

- **WHEN** duration is requested via GET /view or returned from POST /query bootstrap
- **THEN** the response SHALL include `avgReleasedHours`: `AVG(HOLD_HOURS)` over rows where `RELEASETXNDATE IS NOT NULL` after applying `hold_type`, `record_type`, and `reason` filters
- **AND** the response SHALL include `avgOnHoldHours`: `AVG(HOLD_HOURS)` over rows where `RELEASETXNDATE IS NULL` after applying the same filters
- **AND** the response SHALL include `maxReleasedHours`: `MAX(HOLD_HOURS)` over rows where `RELEASETXNDATE IS NOT NULL` after applying the same filters
- **AND** the response SHALL include `maxOnHoldHours`: `MAX(HOLD_HOURS)` over rows where `RELEASETXNDATE IS NULL` after applying the same filters
- **AND** all four values SHALL be numeric (rounded to 2 decimal places) or `0` when no matching rows exist
- **AND** all four values SHALL be computed consistently across the Oracle SQL path (`duration.sql`), the DuckDB SQL runtime path (`hold_history_sql_runtime._query_duration`), and the client-side DuckDB-WASM path (`useHoldHistoryDuckDB.queryDuration`)

#### Scenario: Duration payload shape

- **WHEN** a client receives the duration section of any hold-history response
- **THEN** the payload SHALL match `{ items: [{ range, count, qty, pct }], avgReleasedHours: number, avgOnHoldHours: number, maxReleasedHours: number, maxOnHoldHours: number }`
- **AND** `items` order and semantics SHALL remain unchanged from prior behavior

### Requirement: Hold History API SHALL provide paginated detail list
The detail list SHALL be paginated from the cached dataset.

#### Scenario: List pagination from cache
- **WHEN** list is requested via GET /view with page and per_page params
- **THEN** the cached DataFrame SHALL be filtered and paginated in-memory
- **THEN** response SHALL include items and pagination metadata

### Requirement: Hold History API SHALL keep department endpoint as separate query
The department endpoint SHALL remain as a separate Oracle query due to its unique person-level aggregation.

#### Scenario: Department endpoint unchanged
- **WHEN** `GET /api/hold-history/department` is called
- **THEN** it SHALL continue to execute its own Oracle query
- **THEN** it SHALL NOT use the dataset cache

### Requirement: Database query execution path
The hold-history service (`hold_history_service.py`) SHALL use `read_sql_df_slow` (dedicated connection) instead of `read_sql_df` (pooled connection) for all Oracle queries.

#### Scenario: Hold history queries use dedicated connection
- **WHEN** any hold-history query is executed (trend, pareto, duration, list)
- **THEN** it uses `read_sql_df_slow` which creates a dedicated Oracle connection outside the pool
- **AND** the connection has a 300-second call_timeout (configurable)
