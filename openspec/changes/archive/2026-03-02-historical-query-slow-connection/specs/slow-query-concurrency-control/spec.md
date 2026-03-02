## ADDED Requirements

### Requirement: Configurable slow query timeout
The system SHALL read `DB_SLOW_CALL_TIMEOUT_MS` from environment/config to determine the default `call_timeout` for `read_sql_df_slow`. The default value SHALL be 300000 (300 seconds).

#### Scenario: Default timeout when no env var set
- **WHEN** `DB_SLOW_CALL_TIMEOUT_MS` is not set in environment
- **THEN** `read_sql_df_slow` uses 300 seconds as call_timeout

#### Scenario: Custom timeout from env var
- **WHEN** `DB_SLOW_CALL_TIMEOUT_MS` is set to 180000
- **THEN** `read_sql_df_slow` uses 180 seconds as call_timeout

#### Scenario: Caller overrides timeout
- **WHEN** caller passes `timeout_seconds=120` to `read_sql_df_slow`
- **THEN** the function uses 120 seconds regardless of config value

### Requirement: Semaphore-based concurrency control
The system SHALL use a global `threading.Semaphore` to limit the number of concurrent `read_sql_df_slow` executions. The limit SHALL be configurable via `DB_SLOW_MAX_CONCURRENT` with a default of 3.

#### Scenario: Concurrent queries within limit
- **WHEN** 2 slow queries are running and a 3rd is submitted (limit=3)
- **THEN** the 3rd query proceeds immediately

#### Scenario: Concurrent queries exceed limit
- **WHEN** 3 slow queries are running and a 4th is submitted (limit=3)
- **THEN** the 4th query waits up to 60 seconds for a slot
- **AND** if no slot becomes available, raises RuntimeError with message indicating all slots are busy

#### Scenario: Semaphore release on query failure
- **WHEN** a slow query raises an exception during execution
- **THEN** the semaphore slot is released in the finally block

### Requirement: Slow query active count diagnostic
The system SHALL expose the current number of active slow queries via `get_slow_query_active_count()` and include it in `get_pool_status()` as `slow_query_active`.

#### Scenario: Active count in pool status
- **WHEN** 2 slow queries are running
- **THEN** `get_pool_status()` returns `slow_query_active: 2`

### Requirement: Gunicorn timeout accommodates slow queries
The Gunicorn worker timeout SHALL be at least 360 seconds to accommodate the maximum slow query duration (300s) plus overhead.

#### Scenario: Long query does not kill worker
- **WHEN** a slow query takes 280 seconds to complete
- **THEN** the Gunicorn worker does not timeout and the response is delivered

### Requirement: Config settings in all environments
All environment configs (Config, DevelopmentConfig, ProductionConfig, TestingConfig) SHALL define `DB_SLOW_CALL_TIMEOUT_MS` and `DB_SLOW_MAX_CONCURRENT`.

#### Scenario: Testing config uses short timeout
- **WHEN** running in testing environment
- **THEN** `DB_SLOW_CALL_TIMEOUT_MS` defaults to 10000 and `DB_SLOW_MAX_CONCURRENT` defaults to 1
