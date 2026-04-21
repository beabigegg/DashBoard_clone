# runtime-resilience-recovery Specification

## Purpose
TBD - created by archiving change stability-and-frontend-compute-shift. Update Purpose after archive.
## Requirements
### Requirement: Database Pool Runtime Configuration SHALL Be Enforced
The system SHALL apply database pool and timeout parameters from runtime configuration to the active SQLAlchemy engine used by request handling.

#### Scenario: Runtime pool configuration takes effect
- **WHEN** operators set pool and timeout values via environment configuration and start the service
- **THEN** the active engine MUST use those values for pool size, overflow, wait timeout, and query call timeout

#### Scenario: Slow query semaphore capacity
- **WHEN** the service starts in production or staging configuration
- **THEN** `DB_SLOW_MAX_CONCURRENT` SHALL default to 5 (env: `DB_SLOW_MAX_CONCURRENT`)
- **WHEN** the service starts in development configuration
- **THEN** `DB_SLOW_MAX_CONCURRENT` SHALL default to 3
- **WHEN** the service starts in testing configuration
- **THEN** `DB_SLOW_MAX_CONCURRENT` SHALL remain at 1

### Requirement: Pool Exhaustion MUST Return Retry-Aware Degraded Responses
The system MUST return explicit degraded responses for connection pool exhaustion and include machine-readable metadata for retry/backoff behavior.

#### Scenario: Pool exhausted under load
- **WHEN** concurrent requests exceed available database connections and pool wait timeout is reached
- **THEN** the API MUST return a dedicated error code and retry guidance instead of a generic 500 failure

### Requirement: Runtime Degradation MUST Integrate Circuit Breaker State
Database-facing API behavior SHALL distinguish circuit-breaker-open degradation from transient query failures.

#### Scenario: Circuit breaker is open
- **WHEN** the circuit breaker transitions to OPEN state
- **THEN** database-backed endpoints MUST fail fast with a stable degradation response contract

### Requirement: Worker Recovery SHALL Support Hot Reload and Watchdog-Assisted Recovery
The runtime MUST support graceful worker hot reload and watchdog-triggered recovery without requiring a port change or full system reboot.

#### Scenario: Worker restart requested
- **WHEN** an authorized operator requests worker restart during degraded operation
- **THEN** the service MUST trigger graceful reload and preserve single-port availability

### Requirement: Report Frontend API Access SHALL Honor Degraded Retry Contracts
Report pages SHALL use retry-aware API access paths for JSON endpoints so degraded backend responses propagate retry metadata to UI behavior.

#### Scenario: Pool exhaustion or circuit-open response
- **WHEN** report API endpoints return degraded error codes with retry hints
- **THEN** frontend calls MUST flow through MesApi-compatible behavior and avoid aggressive uncontrolled retry loops

### Requirement: Runtime Resilience Diagnostics MUST Expose Actionable Signals
The system MUST expose machine-readable resilience thresholds, restart-churn indicators, and operator action recommendations so degraded states can be triaged consistently.

#### Scenario: Health payload includes resilience diagnostics
- **WHEN** clients call `/health` or `/health/deep`
- **THEN** responses MUST include resilience thresholds and a recommendation field describing whether to observe, throttle, or trigger controlled worker recovery

#### Scenario: Admin status includes restart churn summary
- **WHEN** operators call `/admin/api/system-status` or `/admin/api/worker/status`
- **THEN** responses MUST include bounded restart history summary within a configured time window and indicate whether churn threshold is exceeded

### Requirement: Recovery Recommendations SHALL Reflect Self-Healing Policy State
Health and admin resilience payloads MUST expose whether automated recovery is allowed, cooling down, or blocked by churn policy.

#### Scenario: Operator inspects degraded state
- **WHEN** `/health` or `/admin/api/worker/status` is requested during degradation
- **THEN** response MUST include policy state, cooldown remaining time, and next recommended action

### Requirement: Manual Recovery Override SHALL Be Explicit and Controlled
Manual restart actions MUST bypass automatic block only through authenticated operator pathways with explicit acknowledgement.

#### Scenario: Churn-blocked state with manual override request
- **WHEN** authorized admin requests manual restart while auto-recovery is blocked
- **THEN** system MUST execute controlled restart path and log the override context for auditability

### Requirement: Circuit Breaker State Transitions SHALL Avoid Lock-Held Logging
Circuit breaker state transitions MUST avoid executing logger I/O while internal state locks are held.

#### Scenario: State transition occurs
- **WHEN** circuit breaker transitions between CLOSED, OPEN, or HALF_OPEN
- **THEN** lock-protected section MUST complete state mutation before emitting transition log output

#### Scenario: Slow log handler under load
- **WHEN** logger handlers are slow or blocked
- **THEN** circuit breaker lock contention MUST remain bounded and MUST NOT serialize unrelated request paths behind logging latency

### Requirement: Health Endpoints SHALL Use Short Internal Memoization
Health and deep-health computation SHALL use a short-lived internal cache to prevent probe storms from amplifying backend load.

#### Scenario: Frequent monitor scrapes
- **WHEN** health endpoints are called repeatedly within a small window
- **THEN** service SHALL return memoized payload for up to 5 seconds in non-testing environments

#### Scenario: Testing mode
- **WHEN** app is running in testing mode
- **THEN** health endpoint memoization MUST be bypassed to preserve deterministic tests

### Requirement: Logs MUST Redact Connection Secrets
Runtime logs MUST avoid exposing DB connection credentials.

#### Scenario: Connection string appears in log message
- **WHEN** a log message contains DB URL credentials
- **THEN** logger output MUST redact password and sensitive userinfo before emission

### Requirement: Oracle driver errors SHALL map to stable API response contracts
Raw Oracle driver exceptions reaching the Flask application boundary SHALL be
translated into stable API envelopes based on their ORA code rather than falling
through to the generic internal-error handler.

#### Scenario: ORA-01017 maps to database connection failure
- **WHEN** a request path raises an Oracle driver error with code `ORA-01017`
- **THEN** the API SHALL return a database-connection failure contract instead
  of generic `INTERNAL_ERROR`
- **THEN** the response SHALL NOT leak the raw driver message untrimmed

#### Scenario: Listener and connection-loss errors return retry-aware degraded response
- **WHEN** a request path raises `ORA-12514`, `ORA-12541`, `ORA-03113`, or
  `ORA-03135`
- **THEN** the API SHALL return HTTP 503 with a machine-readable database
  connection failure code
- **THEN** the response SHALL include `Retry-After`

#### Scenario: ORA-01555 maps to query-timeout contract
- **WHEN** a request path raises `ORA-01555`
- **THEN** the API SHALL return the query-timeout/retryable contract instead of
  generic `INTERNAL_ERROR`

#### Scenario: Unknown ORA code remains distinguishable from generic app failure
- **WHEN** a request path raises an unmapped ORA-coded driver error
- **THEN** the API SHALL return a stable database-originated failure contract
- **THEN** the response SHALL remain distinguishable from non-database generic
  application failures

