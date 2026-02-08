## ADDED Requirements

### Requirement: Vite Page Modules SHALL Reuse Shared Chart and Query Building Blocks
Page entry modules MUST consume shared chart/query/drawer utilities for common behaviors.

#### Scenario: Common chart behavior across pages
- **WHEN** multiple report pages render equivalent chart interactions
- **THEN** the behavior MUST be provided by shared Vite modules rather than duplicated page-local implementations

### Requirement: Modularization MUST Preserve Established Navigation and Drill-Down Semantics
Refactoring into Vite modules SHALL not alter existing page transitions, independent tabs, and drill-down entry points.

#### Scenario: User follows existing drill-down path
- **WHEN** the user navigates from summary page to detail views
- **THEN** the resulting flow and parameter semantics MUST match the established baseline behavior

### Requirement: Module Boundaries SHALL Support Frontend Compute Expansion
Vite module structure MUST keep compute logic decoupled from DOM wiring so additional backend-to-frontend computation shifts can be added safely.

#### Scenario: Adding a new frontend-computed metric
- **WHEN** a new metric is migrated from backend to frontend
- **THEN** the metric logic MUST be integrated through shared compute modules without rewriting page routing structure
