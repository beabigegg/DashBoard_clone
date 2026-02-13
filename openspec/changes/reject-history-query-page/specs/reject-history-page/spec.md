## ADDED Requirements

### Requirement: Reject History page SHALL provide filterable historical query controls
The page SHALL provide a filter area for date range and major production dimensions to drive all report sections.

#### Scenario: Default filter values
- **WHEN** the page is first loaded
- **THEN** `start_date` and `end_date` SHALL default to a valid recent range
- **THEN** all other dimension filters SHALL default to empty (no restriction)

#### Scenario: Apply and clear filters
- **WHEN** user clicks "查詢"
- **THEN** summary, trend, pareto, and list sections SHALL reload with the same filter set
- **WHEN** user clicks "清除條件"
- **THEN** all filters SHALL reset to defaults and all sections SHALL reload

### Requirement: Reject History page SHALL present KPI cards with split reject/defect semantics
The page SHALL display KPI cards that simultaneously show charge-off reject and non-charge-off defect metrics.

#### Scenario: KPI cards render core metrics
- **WHEN** summary data is loaded
- **THEN** cards SHALL include `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, `REJECT_RATE_PCT`, `DEFECT_RATE_PCT`, `REJECT_SHARE_PCT`, `AFFECTED_LOT_COUNT`, and `AFFECTED_WORKORDER_COUNT`
- **THEN** numbers SHALL use zh-TW formatting

#### Scenario: Visual distinction for semantic lanes
- **WHEN** KPI cards are rendered
- **THEN** reject-related cards SHALL use a warm-color visual lane
- **THEN** defect-related cards SHALL use a cool-color visual lane
- **THEN** page legend/badge text SHALL explicitly indicate charge-off vs non-charge-off meaning

### Requirement: Reject History page SHALL display quantity and rate trends in separate charts
The page SHALL show both quantity trend and rate trend to avoid mixing unit scales.

#### Scenario: Quantity trend chart
- **WHEN** trend data is loaded
- **THEN** the quantity trend chart SHALL show `REJECT_TOTAL_QTY` and `DEFECT_QTY` over time
- **THEN** the chart SHALL use a shared X-axis by date bucket

#### Scenario: Rate trend chart
- **WHEN** trend data is loaded
- **THEN** the rate trend chart SHALL show `REJECT_RATE_PCT` and `DEFECT_RATE_PCT` over time
- **THEN** rate values SHALL be displayed as percentages

### Requirement: Reject History page SHALL provide reason Pareto analysis
The page SHALL provide a Pareto view for loss reasons and support downstream filtering.

#### Scenario: Pareto rendering and ordering
- **WHEN** reason Pareto data is loaded
- **THEN** items SHALL be sorted by selected metric descending
- **THEN** a cumulative percentage line SHALL be shown

#### Scenario: Pareto click filtering
- **WHEN** user clicks a Pareto bar or row
- **THEN** the selected reason SHALL become an active filter chip
- **THEN** detail list SHALL reload with that reason
- **THEN** clicking the same reason again SHALL clear the reason filter

### Requirement: Reject History page SHALL show paginated detail rows
The page SHALL provide a paginated detail table for investigation and traceability.

#### Scenario: Detail columns
- **WHEN** list data is loaded
- **THEN** each row SHALL include date, workcenter group, workcenter, product dimensions, reason/category, `MOVEIN_QTY`, `REJECT_TOTAL_QTY`, `DEFECT_QTY`, and component reject columns

#### Scenario: Pagination behavior
- **WHEN** total records exceed per-page size
- **THEN** Prev/Next and page summary SHALL be shown
- **THEN** changing any filter SHALL reset page to 1

### Requirement: Reject History page SHALL support CSV export from current filter context
The page SHALL allow users to export records using the exact active filters.

#### Scenario: Export with current filters
- **WHEN** user clicks "匯出 CSV"
- **THEN** export request SHALL include the current filter state and active reason filter
- **THEN** downloaded file SHALL contain both `REJECT_TOTAL_QTY` and `DEFECT_QTY`

### Requirement: Reject History page SHALL provide robust feedback states
The page SHALL provide loading, empty, and error states without breaking interactions.

#### Scenario: Initial loading
- **WHEN** first query is running
- **THEN** a loading overlay or skeleton SHALL be visible until required data sections are ready

#### Scenario: API failure
- **WHEN** any section API fails
- **THEN** a visible error banner SHALL be shown
- **THEN** already loaded sections SHALL remain interactive

#### Scenario: Empty dataset
- **WHEN** query returns no rows
- **THEN** chart and table areas SHALL show explicit empty-state messages

### Requirement: Reject History page SHALL maintain responsive visual hierarchy
The page SHALL keep the same semantic grouping across desktop and mobile layouts.

#### Scenario: Desktop layout
- **WHEN** viewport is desktop width
- **THEN** KPI cards SHALL render in multi-column layout
- **THEN** trend and pareto sections SHALL render as two-column analytical panels

#### Scenario: Mobile layout
- **WHEN** viewport width is below responsive breakpoint
- **THEN** cards and chart panels SHALL stack in a single column
- **THEN** filter controls SHALL remain operable without horizontal overflow
