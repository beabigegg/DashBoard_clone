## ADDED Requirements

### Requirement: Health endpoints SHALL preserve stable top-level payload contract during API response unification
The health endpoints consumed by shell and operations tooling SHALL preserve their top-level response fields during API contract migration and SHALL not be forced into the generic API envelope.

#### Scenario: `/health` payload stability
- **WHEN** clients request `GET /health`
- **THEN** response payload SHALL expose top-level `status` and `services` fields used by shell health widgets
- **THEN** payload SHALL remain directly consumable without requiring `data.status` indirection

#### Scenario: `/health/deep` payload stability
- **WHEN** clients request `GET /health/deep`
- **THEN** response payload SHALL keep current top-level diagnostic structure (`status`, `checks`, `metrics`, `resilience`)
- **THEN** contract migration SHALL NOT break existing monitoring and troubleshooting reads

#### Scenario: `/health/frontend-shell` payload stability
- **WHEN** clients request `GET /health/frontend-shell`
- **THEN** response payload SHALL keep summary/detail-oriented top-level fields used by shell health UI
- **THEN** contract migration SHALL preserve backward compatibility with existing frontend health components

### Requirement: Health endpoints SHALL be explicitly registered as contract exceptions
Health endpoints SHALL be listed in the migration exception registry so contract enforcement checks do not flag them as non-compliant standard JSON APIs.

#### Scenario: Contract conformance checks run
- **WHEN** automated contract checks scan API endpoints
- **THEN** `/health`, `/health/deep`, and `/health/frontend-shell` SHALL be treated as approved exceptions
- **THEN** checks SHALL still enforce stability assertions for their documented top-level fields
