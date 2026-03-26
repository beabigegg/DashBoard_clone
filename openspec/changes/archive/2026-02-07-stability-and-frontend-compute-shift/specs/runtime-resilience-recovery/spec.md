## ADDED Requirements

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
