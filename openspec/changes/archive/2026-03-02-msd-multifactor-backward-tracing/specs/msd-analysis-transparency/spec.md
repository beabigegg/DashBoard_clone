## ADDED Requirements

### Requirement: Analysis page SHALL display a collapsible analysis summary panel
The page SHALL show a summary panel above KPI cards explaining the query context, data scope, and attribution methodology.

#### Scenario: Summary panel rendering
- **WHEN** backward analysis data is loaded
- **THEN** a collapsible panel SHALL appear above the KPI cards
- **THEN** the panel SHALL be expanded by default on first render
- **THEN** the panel SHALL include a toggle control to collapse/expand

#### Scenario: Query context section
- **WHEN** the summary panel is rendered
- **THEN** it SHALL display the committed query parameters: detection station name, date range (or container mode info), and selected loss reasons (or「全部」if none selected)

#### Scenario: Data scope section
- **WHEN** the summary panel is rendered
- **THEN** it SHALL display:
  - 偵測站 LOT 總數 (total detection lots count)
  - 總投入 (total input qty in pcs)
  - 報廢 LOT 數 (lots with defects matching selected loss reasons)
  - 報廢總數 (total reject qty in pcs)
  - 血緣追溯涵蓋上游 LOT 數 (total unique ancestor count)

#### Scenario: Ancestor count from lineage response
- **WHEN** lineage stage returns response
- **THEN** the response SHALL include `total_ancestor_count` (number of unique ancestor CIDs across all seeds, excluding seeds themselves)
- **THEN** the summary panel SHALL use this value for「血緣追溯涵蓋上游 LOT」

#### Scenario: Attribution methodology section
- **WHEN** the summary panel is rendered
- **THEN** it SHALL display a static text block explaining the attribution logic:
  - All LOTs passing through the detection station (including those with no defects) are included in analysis
  - Each LOT's upstream lineage (split/merge chain) is traced to identify associated upstream factors
  - Attribution rate = sum of associated LOTs' reject qty / sum of associated LOTs' input qty × 100%
  - The same defect can be attributed to multiple upstream factors (non-exclusive)
  - Pareto bar height = attributed defect count (with overlap), orange line = attributed defect rate

#### Scenario: Summary panel in container mode
- **WHEN** query mode is container mode
- **THEN** the query context section SHALL show the input type, resolved count, and not-found count instead of date range
- **THEN** the data scope section SHALL still show LOT count and input/reject totals

#### Scenario: Summary panel collapsed state persistence
- **WHEN** user collapses the summary panel
- **THEN** the collapsed state SHALL persist within the current session (sessionStorage)
- **WHEN** user triggers a new query
- **THEN** the panel SHALL remain in its current collapsed/expanded state
