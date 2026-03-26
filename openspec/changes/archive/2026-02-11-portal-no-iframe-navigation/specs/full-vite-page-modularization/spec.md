## MODIFIED Requirements

### Requirement: Major Pages SHALL be Managed by Vite Modules
The system SHALL provide Vite-managed module entries for major portal pages under a phased SPA-shell migration while keeping direct route access compatible.

#### Scenario: Portal shell module loading
- **WHEN** the portal experience is rendered
- **THEN** shell behavior MUST load from Vite-built module assets when available

#### Scenario: Module fallback continuity
- **WHEN** a required Vite asset is unavailable in a migration phase
- **THEN** the system MUST keep affected page behavior functional through explicit fallback logic

### Requirement: Modularization MUST Preserve Established Navigation and Drill-Down Semantics
Refactoring into Vite modules and SPA shell routing SHALL not alter existing route paths, query semantics, and drill-down entry points.

#### Scenario: User follows existing drill-down path
- **WHEN** the user navigates from summary page to detail views
- **THEN** the resulting flow and parameter semantics MUST match the established baseline behavior

#### Scenario: Direct detail route remains valid
- **WHEN** users open existing detail routes directly with query parameters (e.g., `/wip-detail?workcenter=...`, `/hold-detail?reason=...`)
- **THEN** route-level behavior MUST remain compatible with established baseline expectations
