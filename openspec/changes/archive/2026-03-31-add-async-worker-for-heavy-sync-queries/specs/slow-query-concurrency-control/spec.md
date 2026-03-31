## MODIFIED Requirements

### Requirement: Slow query pool pressure reduction
The slow query pool (`DB_SLOW_MAX_CONCURRENT` semaphore) SHALL experience reduced contention from Gunicorn workers after production-history and yield-alert queries are offloaded to dedicated RQ worker processes. Each RQ worker runs in its own process with independent `DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1`, outside the Gunicorn slow pool.

#### Scenario: Production history queries no longer consume Gunicorn slow pool slots
- **WHEN** a production-history query is routed to the RQ worker
- **THEN** it SHALL NOT acquire a slot from the Gunicorn process's `DB_SLOW_MAX_CONCURRENT` semaphore

#### Scenario: Yield alert queries no longer consume Gunicorn slow pool slots
- **WHEN** a yield-alert query is routed to the RQ worker
- **THEN** it SHALL NOT acquire a slot from the Gunicorn process's `DB_SLOW_MAX_CONCURRENT` semaphore

#### Scenario: RQ unavailable fallback still uses slow pool
- **WHEN** a query falls back to synchronous execution (RQ unavailable)
- **THEN** it SHALL use the Gunicorn slow pool as before (graceful degradation)
