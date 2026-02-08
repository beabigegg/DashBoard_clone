## ADDED Requirements

### Requirement: Health Endpoints SHALL Expose Pool Saturation and Degradation Reason Codes
Operational health endpoints MUST report connection pool saturation indicators and explicit degradation reason codes.

#### Scenario: Pool saturation observed
- **WHEN** checked-out connections and overflow approach configured limits
- **THEN** deep health output MUST expose saturation metrics and degraded reason classification

### Requirement: Degraded Responses MUST Be Correlatable Across API and Health Telemetry
Error responses for degraded states SHALL include stable codes that can be mapped to health telemetry and operational dashboards.

#### Scenario: Degraded API response correlation
- **WHEN** an API request fails due to circuit-open or pool-exhausted conditions
- **THEN** operators MUST be able to match the response code to current health telemetry state

### Requirement: Operational Alert Thresholds SHALL Be Explicitly Defined
The system MUST define alert thresholds for sustained degraded state, repeated worker recovery, and abnormal retry pressure.

#### Scenario: Sustained degradation threshold exceeded
- **WHEN** degraded status persists beyond configured duration
- **THEN** the monitoring contract MUST classify the service as alert-worthy with actionable context
