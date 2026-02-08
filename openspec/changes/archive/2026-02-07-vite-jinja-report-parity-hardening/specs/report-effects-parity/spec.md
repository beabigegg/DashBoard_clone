## ADDED Requirements

### Requirement: Report Effect Parity SHALL Be Preserved During Vite Migration
The system SHALL preserve existing Jinja-era report interactions when report pages are served by Vite modules.

#### Scenario: WIP overview interactions remain equivalent
- **WHEN** users operate WIP overview filters, KPI cards, chart refresh, and drill-down entry
- **THEN** the resulting state transitions and navigation parameters MUST remain behaviorally equivalent to the baseline page logic

#### Scenario: WIP detail interactions remain equivalent
- **WHEN** users operate WIP detail filters, pagination, lot detail popup, and back-to-overview transitions
- **THEN** the resulting data scope and interaction behavior MUST match baseline semantics

### Requirement: Report Visual Semantics MUST Remain Consistent
Report pages SHALL keep established status color semantics, KPI display rules, and table/chart synchronization behavior after migration.

#### Scenario: KPI and matrix state consistency
- **WHEN** metric values are zero or filters target specific matrix levels
- **THEN** KPI values and selected-state highlights MUST render correctly without collapsing valid zero values or losing selection state
