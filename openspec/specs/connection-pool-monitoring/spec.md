## ADDED Requirements

### Requirement: Connection pool status in performance detail
The performance-detail API SHALL include `db_pool` section with `status` (checked_out, checked_in, overflow, max_capacity, saturation) from `get_pool_status()` and `config` (pool_size, max_overflow, pool_timeout, pool_recycle) from `get_pool_runtime_config()`.

#### Scenario: Pool status retrieved
- **WHEN** the API is called
- **THEN** `db_pool.status` SHALL contain current pool utilization metrics and `db_pool.config` SHALL contain the pool configuration values

#### Scenario: Saturation calculation
- **WHEN** the pool has 8 checked_out connections and max_capacity is 30
- **THEN** saturation SHALL be reported as approximately 26.7%

### Requirement: Direct Oracle connection counter
The system SHALL maintain a thread-safe monotonic counter in `database.py` that increments each time `get_db_connection()` or `read_sql_df_slow()` successfully creates a direct (non-pooled) Oracle connection.

#### Scenario: Counter increments on direct connection
- **WHEN** `get_db_connection()` successfully creates a connection
- **THEN** the direct connection counter SHALL increment by 1

#### Scenario: Counter in performance detail
- **WHEN** the performance-detail API is called
- **THEN** `direct_connections` SHALL contain `total_since_start` (counter value) and `worker_pid` (current process PID)

#### Scenario: Counter is per-worker
- **WHEN** multiple gunicorn workers are running
- **THEN** each worker SHALL maintain its own independent counter, and the API SHALL return the counter for the responding worker
