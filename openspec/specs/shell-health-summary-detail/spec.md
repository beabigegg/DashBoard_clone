# shell-health-summary-detail Specification

## Purpose
TBD - created by archiving change portal-shell-route-view-integration. Update Purpose after archive.
## Requirements
### Requirement: Shell health widget SHALL default to compact summary
The shell header SHALL display a compact health summary that communicates overall connection status without rendering full diagnostics inline.

#### Scenario: Compact summary on initial render
- **WHEN** users open `portal-shell`
- **THEN** the header SHALL show health status indicator and short summary text only
- **THEN** detailed subsystem fields SHALL NOT be expanded by default

#### Scenario: Summary reflects aggregated status changes
- **WHEN** backend or shell health status changes between healthy/degraded/unhealthy
- **THEN** the compact summary label and status indicator SHALL update to the new aggregated state

### Requirement: Shell health diagnostics SHALL be disclosed on explicit user interaction
Detailed diagnostics SHALL be available from the shell health widget through explicit user action (click/toggle), while preserving navigation readability.

#### Scenario: Open health detail diagnostics
- **WHEN** a user clicks the health summary widget
- **THEN** the shell SHALL expand or open the diagnostics panel
- **THEN** the panel SHALL include backend and frontend-shell diagnostic items needed for troubleshooting

#### Scenario: Close diagnostics without side effects
- **WHEN** a user clicks outside the diagnostics panel or toggles the widget again
- **THEN** the diagnostics panel SHALL close
- **THEN** current route and page state SHALL remain unchanged

### Requirement: Health diagnostics SHALL remain actionable when health endpoints degrade
The widget SHALL provide a deterministic fallback summary and detail state when one or more health endpoints are unavailable.

#### Scenario: Health endpoint error fallback
- **WHEN** `/health` or `/health/frontend-shell` fails to return a successful response
- **THEN** the summary SHALL indicate degraded or unreachable state
- **THEN** the diagnostics panel SHALL show fallback values or error context instead of empty content

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

