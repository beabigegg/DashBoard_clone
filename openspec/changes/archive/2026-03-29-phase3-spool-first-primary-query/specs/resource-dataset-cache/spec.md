## MODIFIED Requirements

### Requirement: Resource dataset cache SHALL handle cache expiry gracefully
The module SHALL return appropriate signals when cache has expired or the view engine cannot compute a result.

#### Scenario: Cache expired during view request
- **WHEN** a view is requested with a query_id whose spool file has expired
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)

#### Scenario: DuckDB runtime failure during view request
- **WHEN** `apply_view()` is called and the DuckDB SQL runtime returns no result (spool miss, runtime error, or feature flag disabled)
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }`
- **THEN** the HTTP status SHALL be 410 (Gone)
- **THEN** the system SHALL NOT call `_get_cached_df()` or any `_derive_*()` pandas function

## REMOVED Requirements

### Requirement: Resource dataset cache SHALL derive KPI summary from cached DataFrame
**Reason**: KPI derivation is now exclusively handled by `resource_history_sql_runtime.py` via DuckDB SQL. The pandas `_derive_kpi()` function and its callers are deleted as part of Phase 3.
**Migration**: All KPI computation is performed by the DuckDB SQL runtime. No pandas DataFrame is loaded during the view path.

### Requirement: Resource dataset cache SHALL derive trend data from cached DataFrame
**Reason**: Trend derivation is now exclusively handled by DuckDB SQL runtime. The pandas `_derive_trend()` function is deleted.
**Migration**: DuckDB SQL runtime handles trend aggregation via SQL GROUP BY and date functions.

### Requirement: Resource dataset cache SHALL derive heatmap from cached DataFrame
**Reason**: Heatmap derivation is now exclusively handled by DuckDB SQL runtime. The pandas `_derive_heatmap()` function is deleted.
**Migration**: DuckDB SQL runtime computes workcenter × date OU% matrix via SQL aggregation.

### Requirement: Resource dataset cache SHALL derive workcenter comparison from cached DataFrame
**Reason**: Workcenter comparison derivation is now exclusively handled by DuckDB SQL runtime. The pandas `_derive_comparison()` function is deleted.
**Migration**: DuckDB SQL runtime handles comparison aggregation via SQL GROUP BY workcenter.

### Requirement: Resource dataset cache SHALL derive paginated detail from cached DataFrame
**Reason**: Detail derivation is now exclusively handled by DuckDB SQL runtime. The pandas `_derive_detail()` function is deleted.
**Migration**: DuckDB SQL runtime computes detail records with LIMIT/OFFSET pagination.
