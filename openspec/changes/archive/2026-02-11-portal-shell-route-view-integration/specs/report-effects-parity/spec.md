## MODIFIED Requirements

### Requirement: Report Effect Parity SHALL Be Preserved During Vite Migration
The system SHALL preserve existing report interactions and state transitions when report pages are served through shell route-view migration.

#### Scenario: WIP overview interactions remain equivalent
- **WHEN** users operate WIP overview filters, KPI cards, chart refresh, and drill-down entry
- **THEN** the resulting state transitions and navigation parameters MUST remain behaviorally equivalent to the baseline page logic

#### Scenario: WIP detail interactions remain equivalent
- **WHEN** users operate WIP detail filters, pagination, lot detail popup, and back-to-overview transitions
- **THEN** the resulting data scope and interaction behavior MUST match baseline semantics

#### Scenario: Query/filter semantics remain equivalent across shell transitions
- **WHEN** users apply filter combinations and navigate between list/detail pages in shell route-view
- **THEN** request query parameters and returned data scope MUST remain equivalent to the pre-migration baseline

### Requirement: Report Visual Semantics MUST Remain Consistent
Report pages SHALL keep established status color semantics, KPI display rules, and table/chart/matrix synchronization behavior after migration.

#### Scenario: KPI and matrix state consistency
- **WHEN** metric values are zero or filters target specific matrix levels
- **THEN** KPI values and selected-state highlights MUST render correctly without collapsing valid zero values or losing selection state

#### Scenario: Table and chart linked interaction consistency
- **WHEN** users interact with chart selections, legends, or drill actions that influence table/matrix scope
- **THEN** table rows, matrix selections, and highlight states MUST remain synchronized with chart interaction intent

#### Scenario: Chart container lifecycle consistency after route switch
- **WHEN** a chart page is entered via shell navigation or revisited after route transitions
- **THEN** chart layout, tooltip, and interaction targets MUST render correctly without clipped or stale state

### Requirement: Hold Detail Interaction Semantics SHALL Remain Equivalent After Modularization
Migrating hold-detail to a Vite module and shell route-view integration SHALL preserve existing filter, pagination, and refresh behavior.

#### Scenario: User applies filters and paginates on hold-detail
- **WHEN** users toggle age/workcenter/package filters and navigate pages
- **THEN** returned lots, distribution highlights, and pagination state MUST remain behaviorally equivalent to baseline inline behavior

## ADDED Requirements

### Requirement: Report parity evidence SHALL be captured before and after migration
The migration process SHALL produce verifiable pre/post evidence for table, chart, filter, interaction, and matrix parity on each target page.

#### Scenario: Baseline evidence capture before rewrite
- **WHEN** a page enters migration scope
- **THEN** baseline artifacts SHALL be recorded for key workflows, query contracts, and visual/interaction semantics

#### Scenario: Release gate blocks on missing parity evidence
- **WHEN** cutover readiness is evaluated
- **THEN** any page without complete parity evidence or with unresolved critical deviations SHALL block release
