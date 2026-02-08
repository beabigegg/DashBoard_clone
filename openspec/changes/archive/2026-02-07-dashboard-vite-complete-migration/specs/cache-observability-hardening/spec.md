## ADDED Requirements

### Requirement: Layered Cache SHALL Expose Operational State
The route cache implementation SHALL expose layered cache operational state, including mode, freshness, and degradation status.

#### Scenario: Redis unavailable degradation state
- **WHEN** Redis is unavailable
- **THEN** health endpoints MUST indicate degraded cache mode while keeping L1 memory cache active

### Requirement: Cache Telemetry MUST be Queryable for Operations
The system MUST provide cache telemetry suitable for operations diagnostics.

#### Scenario: Telemetry inspection
- **WHEN** operators request deep health status
- **THEN** cache-related metrics/state SHALL be present and interpretable for troubleshooting
