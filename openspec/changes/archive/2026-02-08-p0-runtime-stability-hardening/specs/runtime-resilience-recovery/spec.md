## MODIFIED Requirements

### Requirement: Pool Exhaustion MUST Return Retry-Aware Degraded Responses
The system MUST return explicit degraded responses for connection pool exhaustion, including stable machine-readable retry metadata and HTTP retry hints.

#### Scenario: Pool exhausted under load
- **WHEN** concurrent requests exceed available database connections and pool wait timeout is reached
- **THEN** the API MUST return `DB_POOL_EXHAUSTED` with `retry_after_seconds` metadata and a `Retry-After` header instead of a generic 500 failure

## ADDED Requirements

### Requirement: Runtime Shutdown SHALL Cleanly Stop Background Services
Worker/app shutdown MUST stop long-lived background services and shared clients in deterministic order.

#### Scenario: Worker exits during recycle or graceful reload
- **WHEN** Gunicorn worker shutdown hooks are triggered
- **THEN** cache updater, realtime equipment sync worker, Redis client, and DB engine resources MUST be stopped/disposed without orphan threads

### Requirement: Health Probing SHALL Remain Available During Request-Pool Saturation
Health checks MUST avoid depending solely on the same request pool used by business APIs.

#### Scenario: Request pool saturation
- **WHEN** the main database request pool is exhausted
- **THEN** `/health` and `/health/deep` MUST still provide timely degraded status using isolated probe connectivity
