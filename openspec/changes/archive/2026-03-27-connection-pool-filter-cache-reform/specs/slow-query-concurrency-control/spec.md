## ADDED Requirements

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
