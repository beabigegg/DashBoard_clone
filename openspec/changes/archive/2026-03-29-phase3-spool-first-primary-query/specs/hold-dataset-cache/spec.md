## MODIFIED Requirements

### Requirement: Hold dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired or the view engine cannot compute a result.

#### Scenario: Cache expired during view request
- **WHEN** `apply_view()` is called with a query_id whose spool file has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)

#### Scenario: Cache miss after transition from Redis to spool
- **WHEN** `apply_view()` is called with a query_id that has no spool metadata pointer and no Redis DataFrame key
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }` (treated as expired/miss)
- **THEN** the client SHALL re-trigger `execute_primary_query()`

#### Scenario: DuckDB runtime failure during view request
- **WHEN** `apply_view()` is called and the DuckDB SQL runtime returns no result (spool miss, runtime error, or feature flag disabled)
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)
- **THEN** the system SHALL NOT call `_get_cached_df()` or `_derive_all_views()` pandas function

## REMOVED Requirements

### Requirement: Hold dataset cache SHALL derive trend data from cached DataFrame
**Reason**: Trend derivation is now exclusively handled by `hold_history_sql_runtime.py` via DuckDB SQL. The pandas `_derive_trend()` function and its callers are deleted as part of Phase 3.
**Migration**: DuckDB SQL runtime handles trend aggregation with 07:30 shift boundary logic via SQL date functions.

### Requirement: Hold dataset cache SHALL derive reason Pareto from cached DataFrame
**Reason**: Reason Pareto derivation is now exclusively handled by DuckDB SQL runtime. The pandas `_derive_reason_pareto()` function is deleted.
**Migration**: DuckDB SQL runtime computes reason distribution via SQL GROUP BY HOLDREASONNAME.

### Requirement: Hold dataset cache SHALL derive duration distribution from cached DataFrame
**Reason**: Duration distribution is now exclusively handled by DuckDB SQL runtime. The pandas `_derive_duration()` function is deleted.
**Migration**: DuckDB SQL runtime computes 4-bucket distribution via SQL CASE expressions.

### Requirement: Hold dataset cache SHALL derive paginated list from cached DataFrame
**Reason**: List pagination is now exclusively handled by DuckDB SQL runtime. The pandas `_derive_list()` function is deleted.
**Migration**: DuckDB SQL runtime filters and paginates via SQL WHERE / ORDER BY / LIMIT OFFSET.
