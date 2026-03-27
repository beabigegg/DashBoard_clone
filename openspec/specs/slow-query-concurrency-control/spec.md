## ADDED Requirements

### Requirement: Global Redis-based concurrency limiter for heavy queries
The system SHALL provide a cross-process concurrency limiter using Redis sorted set to limit the total number of concurrent heavy queries across all Gunicorn workers and RQ workers.

#### Scenario: Acquire slot when under limit
- **WHEN** `acquire_heavy_query_slot(owner_id, ttl=600)` is called and current active count < `HEAVY_QUERY_MAX_CONCURRENT` (default 3)
- **THEN** the function SHALL add the owner to the Redis sorted set and return `True`

#### Scenario: Acquire slot when at limit
- **WHEN** `acquire_heavy_query_slot()` is called and current active count >= `HEAVY_QUERY_MAX_CONCURRENT`
- **THEN** the function SHALL return `False` without blocking

#### Scenario: Release slot
- **WHEN** `release_heavy_query_slot(owner_id)` is called
- **THEN** the function SHALL remove the owner from the Redis sorted set

#### Scenario: Expired slot cleanup
- **WHEN** an owner's TTL has expired (score < now - ttl)
- **THEN** the acquire function SHALL remove expired entries before checking the count
- **THEN** this cleanup SHALL happen atomically via Lua script

#### Scenario: Redis unavailable
- **WHEN** Redis is unreachable during `acquire_heavy_query_slot()`
- **THEN** the function SHALL return `True` (fail-open)

## MODIFIED Requirements

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

#### Scenario: Inflight wait default reduced
- **WHEN** `REJECT_ENGINE_QUERY_WAIT_SECONDS` is not set in environment
- **THEN** the default inflight wait SHALL be 90 seconds (changed from 180)
## Requirements
### Requirement: Slow pool capacity matches semaphore
The slow-query connection pool MUST have pool_size + max_overflow equal to the semaphore limit (`DB_SLOW_MAX_CONCURRENT`), ensuring every request that acquires the semaphore can obtain a connection without waiting on pool_timeout.

#### Scenario: Production pool sizing
- **WHEN** the application starts in Production config
- **THEN** `DB_SLOW_POOL_SIZE` SHALL be 5, `DB_SLOW_POOL_MAX_OVERFLOW` SHALL be 3, and `DB_SLOW_MAX_CONCURRENT` SHALL be 8

#### Scenario: Development pool sizing
- **WHEN** the application starts in Development config
- **THEN** `DB_SLOW_POOL_SIZE` + `DB_SLOW_POOL_MAX_OVERFLOW` SHALL equal `DB_SLOW_MAX_CONCURRENT`

### Requirement: Slow path circuit breaker protection
`read_sql_df_slow` MUST check the database circuit breaker before executing queries and record success/failure outcomes, sharing the same circuit breaker instance as `read_sql_df`.

#### Scenario: Circuit breaker open rejects slow query
- **WHEN** the database circuit breaker is in OPEN state
- **AND** `read_sql_df_slow` is called
- **THEN** the function SHALL raise `DatabaseCircuitOpenError` immediately without attempting a connection

#### Scenario: Slow query failure records to circuit breaker
- **WHEN** a slow query raises an Oracle exception
- **THEN** the failure SHALL be recorded to the shared circuit breaker via `record_failure()`

#### Scenario: Slow query success records to circuit breaker
- **WHEN** a slow query completes successfully
- **THEN** the success SHALL be recorded to the shared circuit breaker via `record_success()`

### Requirement: Slow pool keep-alive
The keep-alive background worker MUST ping both main engine and slow engine to prevent idle connections from being terminated by network infrastructure.

#### Scenario: Keep-alive pings slow pool
- **WHEN** the keep-alive worker fires at its interval
- **THEN** it SHALL execute a health-check query (`SELECT 1 FROM DUAL`) on the slow engine in addition to the main engine

#### Scenario: Slow pool keep-alive failure isolation
- **WHEN** the slow engine keep-alive ping fails
- **THEN** the main engine keep-alive SHALL still execute independently

