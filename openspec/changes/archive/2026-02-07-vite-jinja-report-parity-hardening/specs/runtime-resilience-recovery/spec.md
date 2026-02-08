## ADDED Requirements

### Requirement: Report Frontend API Access SHALL Honor Degraded Retry Contracts
Report pages SHALL use retry-aware API access paths for JSON endpoints so degraded backend responses propagate retry metadata to UI behavior.

#### Scenario: Pool exhaustion or circuit-open response
- **WHEN** report API endpoints return degraded error codes with retry hints
- **THEN** frontend calls MUST flow through MesApi-compatible behavior and avoid aggressive uncontrolled retry loops
