## MODIFIED Requirements

### Requirement: Reject History page SHALL provide reason Pareto analysis
The page SHALL display 6 Pareto charts simultaneously (不良原因, PACKAGE, TYPE, WORKFLOW, 站點, 機台) in a 3-column grid layout with cross-filter linkage, replacing the single-dimension dropdown switcher.

#### Scenario: Multi-Pareto grid layout
- **WHEN** Pareto data is loaded
- **THEN** 6 Pareto charts SHALL be rendered simultaneously in a 3-column grid (3×2)
- **THEN** each chart SHALL display one dimension: 不良原因, PACKAGE, TYPE, WORKFLOW, 站點, 機台
- **THEN** there SHALL be no dimension dropdown selector

#### Scenario: Pareto rendering and ordering
- **WHEN** Pareto data is loaded
- **THEN** items in each Pareto SHALL be sorted by selected metric descending
- **THEN** each Pareto SHALL show a cumulative percentage line

#### Scenario: Pareto 80% filter is managed in supplementary filters
- **WHEN** the page first loads Pareto
- **THEN** supplementary filters SHALL include "Pareto 僅顯示累計前 80%" control
- **THEN** the control SHALL default to enabled
- **THEN** the 80% filter SHALL apply uniformly to all 6 Pareto charts

#### Scenario: Cross-filter linkage between Pareto charts
- **WHEN** user clicks an item in one Pareto chart (e.g., selects reason "A")
- **THEN** the other 5 Pareto charts SHALL recalculate with the selection applied as a filter
- **THEN** the clicked Pareto chart itself SHALL NOT be filtered by its own selections
- **THEN** the detail table below SHALL apply ALL selections from ALL dimensions

#### Scenario: Pareto click filtering supports multi-select
- **WHEN** user clicks Pareto bars or table rows in any dimension
- **THEN** clicked items SHALL become active selected chips
- **THEN** multiple selected items SHALL be supported within each dimension
- **THEN** multiple dimensions SHALL support simultaneous selections

#### Scenario: Re-click clears selected item only
- **WHEN** user clicks an already selected Pareto item
- **THEN** only that item SHALL be removed from selection
- **THEN** remaining selected items across all dimensions SHALL stay active
- **THEN** all Pareto charts SHALL recalculate to reflect the updated selections

#### Scenario: Filter chips display all dimension selections
- **WHEN** items are selected across multiple Pareto dimensions
- **THEN** selected items SHALL be displayed as chips grouped by dimension label
- **THEN** each chip SHALL show the dimension label and selected value (e.g., "TYPE: X")
- **THEN** clicking a chip's remove button SHALL deselect that item and trigger recalculation

#### Scenario: Responsive grid layout
- **WHEN** viewport is desktop width (>1200px)
- **THEN** Pareto charts SHALL render in a 3-column grid
- **WHEN** viewport is medium width (768px–1200px)
- **THEN** Pareto charts SHALL render in a 2-column grid
- **WHEN** viewport is below 768px
- **THEN** Pareto charts SHALL stack in a single column

#### Scenario: TOP20/ALL display scope control
- **WHEN** Pareto grid is displayed
- **THEN** supplementary filters SHALL include a global "只顯示 TOP 20" toggle
- **THEN** when enabled, applicable dimensions (TYPE, WORKFLOW, 機台) SHALL truncate to top 20 items
- **THEN** the toggle SHALL apply uniformly to all applicable Pareto charts (not per-chart selectors)
- **THEN** dimensions not in the applicable set (不良原因, PACKAGE, 站點) SHALL be unaffected by this toggle

## MODIFIED Requirements

### Requirement: Reject History page SHALL be structured as modular sub-components
The page template SHALL delegate sections to focused sub-components, following the hold-history architecture pattern.

#### Scenario: Component decomposition
- **WHEN** the page source is examined
- **THEN** the filter panel SHALL be a separate `FilterPanel.vue` component
- **THEN** the KPI summary cards SHALL be a separate `SummaryCards.vue` component
- **THEN** the trend chart SHALL be a separate `TrendChart.vue` component
- **THEN** the pareto grid SHALL be a separate `ParetoGrid.vue` component containing 6 `ParetoSection.vue` instances
- **THEN** each individual pareto chart+table SHALL be a `ParetoSection.vue` component
- **THEN** the detail table with pagination SHALL be a separate `DetailTable.vue` component

#### Scenario: App.vue acts as orchestrator
- **WHEN** the page runs
- **THEN** `App.vue` SHALL hold all reactive state and API logic
- **THEN** sub-components SHALL receive data via props and communicate via events

### Requirement: Reject History page SHALL support CSV export from current filter context
The page SHALL allow users to export records using the exact active filters.

#### Scenario: Export with all active filters
- **WHEN** user clicks "匯出 CSV"
- **THEN** export request SHALL include current primary filters, supplementary filters, trend-date filters, metric filters, and all Pareto-selected items from all 6 dimensions
- **THEN** downloaded file SHALL contain exactly the same rows currently represented by the detail list filter context

#### Scenario: Export remains UTF-8 Excel compatible
- **WHEN** CSV export is downloaded
- **THEN** the file SHALL be encoded in UTF-8 with BOM
- **THEN** Chinese headers and values SHALL render correctly in common spreadsheet tools
