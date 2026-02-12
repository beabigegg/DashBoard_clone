## ADDED Requirements

### Requirement: Frontend and backend route-contract inventories SHALL be cross-validated
Route-governance checks SHALL verify that frontend shell route contracts and backend route contract artifacts describe the same governed route set and scope classes.

#### Scenario: Cross-source contract parity gate
- **WHEN** modernization governance checks run in CI
- **THEN** mismatches between backend route contract JSON and frontend `routeContracts.js` route inventory SHALL fail the gate

#### Scenario: Scope classification drift detection
- **WHEN** a route has inconsistent scope classification between frontend and backend contract sources
- **THEN** governance checks SHALL report the specific route and conflicting scope values

### Requirement: Legacy contract-source fallback SHALL emit operational warning
When contract loading falls back from the primary modernization contract artifact to a legacy artifact path, the service SHALL emit explicit warning telemetry.

#### Scenario: Legacy contract fallback path selected
- **WHEN** the primary contract artifact is unavailable and a legacy contract file is loaded
- **THEN** the system SHALL log a warning that includes the selected legacy source path
