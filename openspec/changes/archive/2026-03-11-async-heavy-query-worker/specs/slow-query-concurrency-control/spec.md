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
