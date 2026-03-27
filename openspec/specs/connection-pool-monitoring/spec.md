## MODIFIED Requirements

### Requirement: Connection pool status in performance detail
The performance-detail API SHALL include `db_pool` section with `status` (checked_out, checked_in, overflow, max_capacity, saturation, slow_query_active, slow_query_waiting) from `get_pool_status()` and `config` (pool_size, max_overflow, pool_timeout, pool_recycle) from `get_pool_runtime_config()`.

#### Scenario: Pool status retrieved
- **WHEN** the API is called
- **THEN** `db_pool.status` SHALL contain current pool utilization metrics including `slow_query_active` and `slow_query_waiting`, and `db_pool.config` SHALL contain the pool configuration values

#### Scenario: Saturation calculation
- **WHEN** the pool has 8 checked_out connections and max_capacity is 30
- **THEN** saturation SHALL be reported as approximately 26.7%

#### Scenario: Slow query waiting included
- **WHEN** 2 threads are waiting for the slow query semaphore
- **THEN** `db_pool.status.slow_query_waiting` SHALL be 2

## ADDED Requirements

### Requirement: Slow-path query latency included in QueryMetrics
The `read_sql_df_slow()` and `read_sql_df_slow_iter()` functions SHALL call `record_query_latency()` with the total elapsed time upon completion, ensuring P50/P95/P99 percentiles reflect queries from all paths (pooled and slow/direct).

#### Scenario: Slow query latency recorded
- **WHEN** `read_sql_df_slow()` completes a query in 8.5 seconds
- **THEN** `record_query_latency(8.5)` SHALL be called and the value SHALL appear in subsequent `get_percentiles()` results

#### Scenario: Slow iter latency recorded
- **WHEN** `read_sql_df_slow_iter()` completes streaming in 45 seconds
- **THEN** `record_query_latency(45.0)` SHALL be called in the finally block
## Requirements
### Requirement: Zero direct connections
All database access MUST go through connection pools (main or slow engine). No code path SHALL use `get_db_connection()` for direct oracledb connections.

#### Scenario: Table utility functions use pool
- **WHEN** `get_table_columns()`, `get_table_data()`, or `get_table_column_metadata()` is called
- **THEN** each function SHALL use `engine.connect()` from the main pool instead of `get_db_connection()`

#### Scenario: Resource status values uses service layer
- **WHEN** the `/resource/status_values` endpoint is called
- **THEN** the route SHALL delegate to a service function that uses `read_sql_df()` (main pool)
- **AND** the route SHALL NOT import or call `get_db_connection()`

#### Scenario: Direct connection counter stays zero
- **WHEN** any API request is processed under normal operation
- **THEN** the direct connection counter SHALL remain at 0

