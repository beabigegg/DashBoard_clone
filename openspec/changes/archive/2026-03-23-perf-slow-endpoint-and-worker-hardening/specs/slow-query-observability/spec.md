## MODIFIED Requirements

### Requirement: Slow query warning log SHALL include caller tag
The `read_sql_df()` and `read_sql_df_slow()` slow query warning logs SHALL include an optional `caller` parameter identifying which service triggered the query.

#### Scenario: Caller tag in slow log
- **WHEN** `read_sql_df(sql, params, caller="reject_dataset_cache")` completes in >1s
- **THEN** the WARNING log SHALL include the caller: `"Slow query (reject_dataset_cache, 5.23s): SELECT ..."`

#### Scenario: No caller tag (backward compatible)
- **WHEN** `read_sql_df(sql, params)` is called without `caller` parameter
- **THEN** the WARNING log SHALL use `"unknown"` as the caller tag

#### Scenario: Caller tag on slow path
- **WHEN** `read_sql_df_slow(sql, params, caller="msd_detection")` completes
- **THEN** the log SHALL include the caller tag in both the slow warning and the debug completion message
