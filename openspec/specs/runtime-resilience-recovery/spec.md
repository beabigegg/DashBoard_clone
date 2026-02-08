# runtime-resilience-recovery Specification

## Purpose
TBD - created by archiving change stability-and-frontend-compute-shift. Update Purpose after archive.
## Requirements
### Requirement: Database Pool Runtime Configuration SHALL Be Enforced
The system SHALL apply database pool and timeout parameters from runtime configuration to the active SQLAlchemy engine used by request handling.

#### Scenario: Runtime pool configuration takes effect
- **WHEN** operators set pool and timeout values via environment configuration and start the service
- **THEN** the active engine MUST use those values for pool size, overflow, wait timeout, and query call timeout

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
