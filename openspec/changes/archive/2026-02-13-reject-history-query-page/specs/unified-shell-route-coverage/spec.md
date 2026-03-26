## ADDED Requirements

### Requirement: Reject History route SHALL be included in governed shell route inventory
The `/reject-history` route SHALL be represented in shell route contracts with complete governance metadata.

#### Scenario: Frontend route contract entry
- **WHEN** route contract validation runs against `frontend/src/portal-shell/routeContracts.js`
- **THEN** `/reject-history` SHALL exist with route id, title, owner, render mode, visibility policy, scope, and compatibility policy

#### Scenario: Native loader coverage
- **WHEN** native module loader registry is validated
- **THEN** `/reject-history` SHALL be resolvable in `nativeModuleRegistry`

### Requirement: Reject History governance metadata SHALL be parity-validated across sources
Shell governance checks SHALL enforce parity for `/reject-history` between frontend and backend contract inventories.

#### Scenario: Contract parity for reject-history route
- **WHEN** contract parity checks execute
- **THEN** frontend and backend route inventories SHALL both include `/reject-history`
- **THEN** metadata mismatch or missing route SHALL fail governance checks

#### Scenario: Navigation visibility governance
- **WHEN** page status/navigation config is evaluated
- **THEN** `/reject-history` SHALL have governed drawer assignment and ordering metadata
