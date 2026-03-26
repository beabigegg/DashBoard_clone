## MODIFIED Requirements

### Requirement: LineageEngine SHALL use non-pooled database connections
All Oracle queries executed by `LineageEngine` SHALL use `read_sql_df_slow()` (dedicated non-pooled connections) instead of `read_sql_df()` (connection pool).

#### Scenario: Lineage query does not consume pool connections
- **WHEN** `LineageEngine` executes split ancestor, merge source, or other Oracle queries
- **THEN** queries SHALL use `read_sql_df_slow()` with the default slow query timeout (300s)
- **THEN** the shared connection pool SHALL NOT be consumed by lineage queries

#### Scenario: Lineage queries respect slow query semaphore
- **WHEN** `LineageEngine` executes queries via `read_sql_df_slow()`
- **THEN** each query SHALL acquire and release a slot from the slow query semaphore (`DB_SLOW_MAX_CONCURRENT`)
