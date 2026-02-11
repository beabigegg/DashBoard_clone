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

