## ADDED Requirements

### Requirement: Slow query active count in metrics history snapshots
The `MetricsHistoryCollector` SHALL include `slow_query_active` in each 30-second snapshot, recording the number of slow queries currently executing via dedicated connections.

#### Scenario: Snapshot includes slow_query_active
- **WHEN** the collector writes a snapshot while 3 slow queries are executing
- **THEN** the `slow_query_active` column SHALL contain the value 3

#### Scenario: No slow queries active
- **WHEN** the collector writes a snapshot while no slow queries are executing
- **THEN** the `slow_query_active` column SHALL contain the value 0

### Requirement: Slow query waiting count tracked and persisted
The system SHALL maintain a thread-safe counter `_SLOW_QUERY_WAITING` in `database.py` that tracks the number of threads currently waiting to acquire the slow query semaphore. This counter SHALL be included in `get_pool_status()` and persisted to metrics history snapshots.

#### Scenario: Counter increments on semaphore wait
- **WHEN** a thread enters `read_sql_df_slow()` and the semaphore is full
- **THEN** `_SLOW_QUERY_WAITING` SHALL be incremented before `semaphore.acquire()` and decremented after acquire completes (success or timeout)

#### Scenario: Counter in pool status API
- **WHEN** `get_pool_status()` is called
- **THEN** the returned dict SHALL include `slow_query_waiting` with the current waiting thread count

#### Scenario: Counter persisted to metrics history
- **WHEN** the collector writes a snapshot
- **THEN** the `slow_query_waiting` column SHALL reflect the count at snapshot time

### Requirement: Slow-path query latency recorded in QueryMetrics
The `read_sql_df_slow()` and `read_sql_df_slow_iter()` functions SHALL call `record_query_latency()` with the elapsed query time, so that P50/P95/P99 metrics reflect all query paths (pool + slow).

#### Scenario: Slow query latency appears in percentiles
- **WHEN** a `read_sql_df_slow()` call completes in 5.2 seconds
- **THEN** `record_query_latency(5.2)` SHALL be called and the latency SHALL appear in subsequent `get_percentiles()` results

#### Scenario: Slow iter latency recorded on completion
- **WHEN** a `read_sql_df_slow_iter()` generator completes after yielding all batches in 120 seconds total
- **THEN** `record_query_latency(120.0)` SHALL be called in the finally block

### Requirement: Slow query metrics displayed in Vue SPA
The admin performance Vue SPA SHALL display `slow_query_active` and `slow_query_waiting` as StatCards in the connection pool panel, and include `slow_query_active` as a trend line in the connection pool trend chart.

#### Scenario: StatCards display current values
- **WHEN** the performance-detail API returns `db_pool.status.slow_query_active = 4` and `db_pool.status.slow_query_waiting = 2`
- **THEN** the connection pool panel SHALL display StatCards showing "慢查詢執行中: 4" and "慢查詢排隊中: 2"

#### Scenario: Trend chart includes slow_query_active
- **WHEN** historical snapshots contain `slow_query_active` data points
- **THEN** the connection pool trend chart SHALL include a "慢查詢執行中" line series
