## MODIFIED Requirements

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
