## ADDED Requirements

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
