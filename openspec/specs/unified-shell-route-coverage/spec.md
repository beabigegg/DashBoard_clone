# unified-shell-route-coverage Specification

## Purpose
TBD - created by archiving change full-modernization-architecture-blueprint. Update Purpose after archive.
## Requirements
### Requirement: In-scope routes SHALL be shell-contract governed
All in-scope modernization routes SHALL be represented in shell route contracts, loader registration policy, and navigation visibility governance.

#### Scenario: In-scope coverage validation
- **WHEN** shell route contract validation is executed
- **THEN** every in-scope route SHALL have route metadata, ownership metadata, and visibility policy metadata
- **THEN** missing in-scope route contracts SHALL fail validation

#### Scenario: Admin route inclusion
- **WHEN** shell navigation is built for admin users
- **THEN** `/admin/pages` and `/admin/performance` SHALL be represented as governed navigation targets according to visibility/access policy

### Requirement: Out-of-scope routes SHALL not block this phase
Routes explicitly marked as out-of-scope for this modernization phase SHALL be excluded from required shell-coverage gates in this phase.

#### Scenario: Deferred route exclusion
- **WHEN** modernization gates execute for this phase
- **THEN** `/tables`, `/excel-query`, `/query-tool`, and `/mid-section-defect` SHALL be treated as deferred routes
- **THEN** deferred route absence from new shell-governance gates SHALL NOT fail this phase

### Requirement: Route coverage governance SHALL be CI-enforced
Route coverage and contract completeness checks for in-scope routes SHALL run as CI gates.

#### Scenario: CI gate failure on in-scope gap
- **WHEN** CI detects an in-scope route without required contract metadata
- **THEN** the modernization gate SHALL fail
- **THEN** release promotion SHALL be blocked until resolved

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

