# reject-history-page Specification

## Purpose
TBD - created by archiving change reject-history-query-page. Update Purpose after archive.
## Requirements
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

#### Scenario: Required core filters are present
- **WHEN** the filter panel is rendered
- **THEN** it SHALL include `start_date/end_date` time filter controls
- **THEN** it SHALL include reason filter control
- **THEN** it SHALL include `WORKCENTER_GROUP` filter control

#### Scenario: Header refresh button
- **WHEN** the page header is rendered
- **THEN** it SHALL include a "重新整理" button in the header-right area
- **WHEN** user clicks the refresh button
- **THEN** all sections SHALL reload with current filters (equivalent to "查詢")

### Requirement: Reject History page SHALL expose yield-exclusion toggle control
The page SHALL let users decide whether to include policy-marked scrap in yield calculations.

#### Scenario: Default toggle state
- **WHEN** the page is first loaded
- **THEN** "納入不計良率報廢" toggle SHALL default to OFF
- **THEN** requests SHALL be sent with `include_excluded_scrap=false`

#### Scenario: Toggle affects all sections
- **WHEN** user turns ON/OFF the toggle and clicks "查詢"
- **THEN** summary, trend, pareto, and list sections SHALL reload under the selected policy mode
- **THEN** export action SHALL use the same toggle state

#### Scenario: Policy status visibility
- **WHEN** data is rendered
- **THEN** the UI SHALL show a clear badge/text indicating whether policy-marked scrap is currently excluded or included

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

#### Scenario: Export with all active filters
- **WHEN** user clicks "匯出 CSV"
- **THEN** export request SHALL include current primary filters, supplementary filters, trend-date filters, metric filters, and all Pareto-selected items from all 6 dimensions
- **THEN** downloaded file SHALL contain exactly the same rows currently represented by the detail list filter context

#### Scenario: Export remains UTF-8 Excel compatible
- **WHEN** CSV export is downloaded
- **THEN** the file SHALL be encoded in UTF-8 with BOM
- **THEN** Chinese headers and values SHALL render correctly in common spreadsheet tools

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

### Requirement: Reject History page SHALL display a loading overlay during initial data load
The page SHALL show a full-screen loading overlay with spinner during the first data load to provide clear feedback.

#### Scenario: Loading overlay on initial mount
- **WHEN** the page first mounts and `loadAllData` begins
- **THEN** a loading overlay with spinner SHALL be displayed over the page content
- **WHEN** all initial API responses complete
- **THEN** the overlay SHALL be hidden

#### Scenario: Subsequent queries do not show overlay
- **WHEN** the user triggers a re-query after initial load
- **THEN** no full-screen overlay SHALL appear (inline loading states are sufficient)

### Requirement: Detail table rows SHALL highlight on hover
The detail table and pareto table rows SHALL visually respond to mouse hover for improved readability.

#### Scenario: Row hover in detail table
- **WHEN** user hovers over a row in the detail table
- **THEN** the row background SHALL change to a subtle highlight color

#### Scenario: Row hover in pareto table
- **WHEN** user hovers over a row in the pareto summary table
- **THEN** the row background SHALL change to a subtle highlight color

### Requirement: Pagination controls SHALL use Chinese labels
The detail list pagination SHALL display controls in Chinese to match the rest of the page language.

#### Scenario: Pagination button labels
- **WHEN** the pagination controls are rendered
- **THEN** the previous-page button SHALL display "上一頁"
- **THEN** the next-page button SHALL display "下一頁"
- **THEN** the page info text SHALL use Chinese formatting (e.g., "第 1 / 5 頁 · 共 250 筆")

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

### Requirement: Reject History page SHALL display partial failure warning banner
The page SHALL display an amber warning banner when the query result contains partial failures, informing users that displayed data may be incomplete.

#### Scenario: Warning banner displayed on partial failure
- **WHEN** the primary query response includes `meta.has_partial_failure: true`
- **THEN** an amber warning banner SHALL be displayed below the error banner position
- **THEN** the warning message SHALL be in Traditional Chinese

#### Scenario: Warning banner shows failed date ranges
- **WHEN** `meta.failed_ranges` contains date range objects
- **THEN** the warning banner SHALL display the specific failed date ranges (e.g., "以下日期區間的資料擷取失敗：2025-01-01 ~ 2025-01-10")

#### Scenario: Warning banner shows generic message without ranges (container mode or missing range data)
- **WHEN** `meta.has_partial_failure` is true but `meta.failed_ranges` is empty or absent (e.g., container-id batch query)
- **THEN** the warning banner SHALL display a generic message with the failed chunk count (e.g., "3 個查詢批次的資料擷取失敗")

#### Scenario: Warning banner cleared on new query
- **WHEN** user initiates a new primary query
- **THEN** the warning banner SHALL be cleared before the new query executes
- **THEN** if the new query also has partial failures, the warning SHALL update with new failure information

#### Scenario: Warning banner coexists with error banner
- **WHEN** both an error message and a partial failure warning exist
- **THEN** the error banner SHALL appear first, followed by the warning banner

#### Scenario: Warning banner visual style
- **WHEN** the warning banner is rendered
- **THEN** it SHALL use amber/orange color scheme (background `#fffbeb`, text `#b45309`)
- **THEN** the style SHALL be consistent with the existing `.resolution-warn` color pattern

### Requirement: Reject History page SHALL validate date range before query submission
The page SHALL validate the date range on the client side before sending the API request, providing immediate feedback for invalid ranges.

#### Scenario: Date range exceeds 730-day limit
- **WHEN** user selects a date range exceeding 730 days and clicks "查詢"
- **THEN** the page SHALL display an error message "查詢範圍不可超過 730 天（約兩年）"
- **THEN** the API request SHALL NOT be sent

#### Scenario: Missing start or end date
- **WHEN** user clicks "查詢" without setting both start_date and end_date (in date_range mode)
- **THEN** the page SHALL display an error message "請先設定開始與結束日期"
- **THEN** the API request SHALL NOT be sent

#### Scenario: End date before start date
- **WHEN** user selects an end_date earlier than start_date
- **THEN** the page SHALL display an error message "結束日期必須大於起始日期"
- **THEN** the API request SHALL NOT be sent

#### Scenario: Valid date range proceeds normally
- **WHEN** user selects a valid date range within 730 days and clicks "查詢"
- **THEN** no validation error SHALL be shown
- **THEN** the API request SHALL proceed normally

#### Scenario: Container mode skips date validation
- **WHEN** query mode is "container" (not "date_range")
- **THEN** date range validation SHALL be skipped

### Requirement: Frontend API timeout
The reject-history page SHALL use a 360-second API timeout (up from 60 seconds) for all Oracle-backed API calls.

#### Scenario: Large date range query completes
- **WHEN** a user queries reject history for a long date range
- **THEN** the frontend does not abort the request for at least 360 seconds

### Requirement: Reject History page SHALL abort active Job polling on unmount
When the Reject History component is destroyed (user navigates away), any active RQ Job polling controller SHALL be aborted immediately to prevent background network activity.

#### Scenario: Polling stops on navigation
- **WHEN** a user triggers a query that initiates an async RQ Job
- **AND** the user navigates away from Reject History before the job completes
- **THEN** the `_jobAbortController` SHALL be aborted in `onUnmounted`
- **THEN** no further requests SHALL be sent to the job status endpoint after component destruction

