## MODIFIED Requirements

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

## ADDED Requirements

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
- **THEN** the pareto section (chart + table) SHALL be a separate `ParetoSection.vue` component
- **THEN** the detail table with pagination SHALL be a separate `DetailTable.vue` component

#### Scenario: App.vue acts as orchestrator
- **WHEN** the page runs
- **THEN** `App.vue` SHALL hold all reactive state and API logic
- **THEN** sub-components SHALL receive data via props and communicate via events
