## ADDED Requirements

### Requirement: Resource History page SHALL display KPI summary cards
The page SHALL show 9 KPI cards with aggregated performance metrics for the queried period.

#### Scenario: KPI cards rendering
- **WHEN** summary data is loaded from `GET /api/resource/history/summary`
- **THEN** 9 cards SHALL display: OU%, AVAIL%, PRD, SBY, UDT, SDT, EGT, NST, Machine Count
- **THEN** hour values SHALL format with "K" suffix for large numbers (e.g., 2.5K)
- **THEN** percentage values SHALL use `buildResourceKpiFromHours()` from `core/compute.js`

### Requirement: Resource History page SHALL display trend chart
The page SHALL show OU% and Availability% trends over time.

#### Scenario: Trend chart rendering
- **WHEN** summary data is loaded
- **THEN** a line chart with area fill SHALL display OU% and AVAIL% time series
- **THEN** the chart SHALL use vue-echarts with `autoresize` prop
- **THEN** smooth curves with 0.2 opacity area style SHALL render

### Requirement: Resource History page SHALL display stacked status distribution chart
The page SHALL show E10 status hour distribution over time.

#### Scenario: Stacked bar chart rendering
- **WHEN** summary data is loaded
- **THEN** a stacked bar chart SHALL display PRD, SBY, UDT, SDT, EGT, NST hours per period
- **THEN** each status SHALL use its designated color (PRD=green, SBY=blue, UDT=red, SDT=yellow, EGT=purple, NST=gray)
- **THEN** tooltips SHALL show percentages calculated dynamically

### Requirement: Resource History page SHALL display workcenter comparison chart
The page SHALL show top workcenters ranked by OU%.

#### Scenario: Comparison chart rendering
- **WHEN** summary data is loaded
- **THEN** a horizontal bar chart SHALL display top 15 workcenters by OU%
- **THEN** bars SHALL be color-coded: green (≥80%), yellow (≥50%), red (<50%)
- **THEN** data SHALL display in descending OU% order (top to bottom)

### Requirement: Resource History page SHALL display OU% heatmap
The page SHALL show a heatmap of OU% by workcenter and date.

#### Scenario: Heatmap chart rendering
- **WHEN** summary data is loaded
- **THEN** a 2D heatmap SHALL display: workcenters (Y-axis) × dates (X-axis)
- **THEN** color scale SHALL range from red (low OU%) through yellow to green (high OU%)
- **THEN** workcenters SHALL sort by `workcenter_seq` for consistent ordering

### Requirement: Resource History page SHALL display hierarchical detail table
The page SHALL show a three-level expandable table with per-resource performance metrics.

#### Scenario: Detail table rendering
- **WHEN** detail data is loaded from `GET /api/resource/history/detail`
- **THEN** a tree table SHALL display with columns: Name, OU%, AVAIL%, PRD, SBY, UDT, SDT, EGT, NST, Count
- **THEN** Level 0 rows SHALL show workcenter groups with aggregated metrics
- **THEN** Level 1 rows SHALL show resource families with aggregated metrics
- **THEN** Level 2 rows SHALL show individual resources

#### Scenario: Hour and percentage display
- **WHEN** detail data renders
- **THEN** status columns SHALL display hours with percentage: "10.5h (25%)"
- **THEN** KPI values SHALL be computed using `buildResourceKpiFromHours()` from `core/compute.js`

#### Scenario: Tree expand and collapse
- **WHEN** user clicks the expand button on a row
- **THEN** child rows SHALL toggle visibility
- **WHEN** user clicks "Expand All" or "Collapse All"
- **THEN** all rows SHALL expand or collapse accordingly

### Requirement: Resource History page SHALL support date range and granularity selection
The page SHALL allow users to specify time range and aggregation granularity.

#### Scenario: Date range selection
- **WHEN** the page loads
- **THEN** date inputs SHALL default to last 7 days (yesterday minus 6 days)
- **THEN** date range SHALL NOT exceed 730 days (2 years)

#### Scenario: Granularity buttons
- **WHEN** user clicks a granularity button (日/週/月/年)
- **THEN** the active button SHALL highlight
- **THEN** the next query SHALL use the selected granularity (day/week/month/year)

#### Scenario: Query execution
- **WHEN** user clicks the query button
- **THEN** summary and detail APIs SHALL be called in parallel
- **THEN** all 4 charts, KPI cards, and detail table SHALL update with results

### Requirement: Resource History page SHALL support multi-select filtering
The page SHALL provide multi-select dropdown filters for workcenter groups and families, and SHALL support interdependent narrowing with machine options and selected-value pruning.

#### Scenario: Multi-select dropdown
- **WHEN** user clicks a multi-select dropdown trigger
- **THEN** a dropdown SHALL display with checkboxes for each option
- **THEN** "Select All" and "Clear All" buttons SHALL be available
- **THEN** clicking outside the dropdown SHALL close it

#### Scenario: Filter options loading
- **WHEN** the page loads
- **THEN** workcenter groups and families SHALL load from `GET /api/resource/history/options`
- **THEN** machine candidates SHALL be derivable before first query from loaded option resources

#### Scenario: Upstream filters narrow downstream options
- **WHEN** user changes upstream filters (`workcenterGroups`, `families`, equipment-type flags)
- **THEN** machine options SHALL be recomputed to only include matching resources
- **THEN** narrowed options SHALL be reflected immediately in filter controls

#### Scenario: Invalid selected machines are pruned
- **WHEN** upstream filters change and selected machines are no longer valid
- **THEN** invalid selected machine values SHALL be removed automatically
- **THEN** remaining valid selected machine values SHALL be preserved

#### Scenario: Equipment type checkboxes
- **WHEN** user toggles a checkbox (生產設備, 重點設備, 監控設備)
- **THEN** the next query SHALL include the corresponding filter parameter
- **THEN** option narrowing SHALL also honor the same checkbox conditions

### Requirement: Resource History page SHALL support CSV export
The page SHALL allow users to export the current query results as CSV.

#### Scenario: CSV export
- **WHEN** user clicks the "匯出 CSV" button
- **THEN** the browser SHALL download a CSV file from `GET /api/resource/history/export` with current filters
- **THEN** the filename SHALL be `resource_history_{start_date}_to_{end_date}.csv`

### Requirement: Resource History page SHALL handle loading and error states
The page SHALL display appropriate feedback during API calls and on errors.

#### Scenario: Query loading state
- **WHEN** a query is executing
- **THEN** the query button SHALL be disabled
- **THEN** a loading indicator SHALL display

#### Scenario: API error handling
- **WHEN** an API call fails
- **THEN** a toast notification SHALL display the error message
- **THEN** the page SHALL NOT crash or become unresponsive

#### Scenario: No data placeholder
- **WHEN** query returns empty results
- **THEN** charts and table SHALL display "No data" placeholders
