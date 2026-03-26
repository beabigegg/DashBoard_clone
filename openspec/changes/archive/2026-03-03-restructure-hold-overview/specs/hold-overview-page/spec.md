## MODIFIED Requirements

### Requirement: Hold Overview page SHALL display a filter bar with Hold Type and Reason
The page SHALL provide a filter bar for selecting hold type and hold reason.

#### Scenario: Hold Type radio default
- **WHEN** the page loads without a `hold_type` URL parameter
- **THEN** the Hold Type filter SHALL default to "全部"
- **THEN** three radio options SHALL display: 品質異常, 非品質異常, 全部

#### Scenario: Hold Type from URL parameter
- **WHEN** the page loads with `?hold_type=quality` or `?hold_type=non-quality`
- **THEN** the Hold Type filter SHALL be set to the specified value

#### Scenario: Hold Type change reloads all data
- **WHEN** user changes the Hold Type selection
- **THEN** all API calls (summary, matrix, hold pareto, lots) SHALL reload with the new hold_type parameter
- **THEN** any active matrix filters SHALL be cleared

#### Scenario: Reason dropdown populated from current data
- **WHEN** summary data is loaded
- **THEN** the Reason dropdown SHALL display "全部" plus all distinct hold reasons from the data
- **THEN** selecting a specific reason SHALL reload all API calls filtered by that reason
- **THEN** any active matrix filters SHALL be cleared

### Requirement: Hold Overview page SHALL display paginated lot details
The page SHALL display a detailed lot table with server-side pagination.

#### Scenario: Lot table rendering
- **WHEN** lot data is loaded from `GET /api/hold-overview/lots`
- **THEN** a table SHALL display with 13 columns: LOTID, WORKORDER, QTY, Product, Package, Workcenter, Hold Reason, Spec, Age, Hold By, Dept, Hold Comment, Future Hold Comment
- **THEN** age values SHALL display with "天" suffix

#### Scenario: Lot table responds to all cascade filters
- **WHEN** matrixFilter is `{ workcenter: WC-A, package: PKG-1 }`
- **THEN** lots API SHALL be called with `workcenter=WC-A&package=PKG-1`
- **THEN** only lots matching all active filters SHALL be displayed

#### Scenario: Pagination
- **WHEN** total lots exceeds per_page (50)
- **THEN** Prev/Next buttons and page info SHALL display
- **THEN** page info SHALL show "顯示 {start} - {end} / {total}"

#### Scenario: Filter changes reset pagination
- **WHEN** any filter changes (filter bar, matrix click, or WIP filter apply)
- **THEN** pagination SHALL reset to page 1

#### Scenario: Empty lot result
- **WHEN** a query returns zero lots
- **THEN** the lot table SHALL display a "No data" placeholder

### Requirement: Hold Overview page SHALL have back navigation
The page SHALL provide navigation back to WIP Overview.

#### Scenario: Back button
- **WHEN** user clicks the "← WIP Overview" button in the header
- **THEN** the page SHALL navigate to `/wip-overview`

## ADDED Requirements

### Requirement: Hold Overview page SHALL display Hold Pareto analysis
The page SHALL display Pareto charts for quality and non-quality hold reasons, fetched from `/api/wip/overview/hold`.

#### Scenario: Pareto chart rendering
- **WHEN** hold data is loaded from `GET /api/wip/overview/hold`
- **THEN** hold items SHALL be split into quality and non-quality groups using `splitHoldByType()`
- **THEN** each group SHALL display an ECharts dual-axis Pareto chart (bar=QTY, line=cumulative %)
- **THEN** items SHALL be sorted by QTY descending
- **THEN** quality chart SHALL use red color (#ef4444), non-quality SHALL use orange (#f97316)

#### Scenario: Pareto visibility by holdType
- **WHEN** holdType is "all"
- **THEN** both quality and non-quality Pareto charts SHALL display
- **WHEN** holdType is "quality"
- **THEN** only the quality Pareto chart SHALL display
- **WHEN** holdType is "non-quality"
- **THEN** only the non-quality Pareto chart SHALL display

#### Scenario: Pareto chart drill-down
- **WHEN** user clicks a bar in the Pareto chart or a reason link in the table
- **THEN** the page SHALL navigate to `/hold-detail?reason={reason}`

#### Scenario: Empty hold data
- **WHEN** a hold type has no items
- **THEN** the chart area SHALL display a "目前無資料" message

### Requirement: Hold Overview page SHALL support WIP-style multi-field filtering
The page SHALL provide the same 6-field FilterPanel as WIP Overview (workorder, lotid, package, type, firstname, waferdesc).

#### Scenario: FilterPanel rendering
- **WHEN** the page loads
- **THEN** a FilterPanel SHALL display with 6 multi-select fields: WORKORDER, LOT ID, PACKAGE, TYPE, Wafer LOT, Wafer Type
- **THEN** filter options SHALL be loaded from `GET /api/wip/meta/filter-options` with `status=HOLD` and current holdType

#### Scenario: Apply filters
- **WHEN** user selects filter values and clicks "套用篩選"
- **THEN** all API calls (summary, matrix, hold pareto, lots) SHALL reload with the filter values
- **THEN** the URL SHALL be updated to include the filter values

#### Scenario: Clear filters
- **WHEN** user clicks "清除篩選"
- **THEN** all filter inputs SHALL be cleared and data SHALL reload without WIP filters
- **THEN** holdType and reason filters SHALL be preserved

#### Scenario: Filter options update
- **WHEN** filters are changed (draft mode)
- **THEN** filter options SHALL reload with debounce (120ms) reflecting cross-filter narrowing

### Requirement: Hold Overview API endpoints SHALL accept WIP filter parameters
The backend Hold Overview endpoints SHALL support optional workorder, lotid, type, firstname, waferdesc query parameters.

#### Scenario: Summary API with WIP filters
- **WHEN** `GET /api/hold-overview/summary?hold_type=quality&workorder=WO-001`
- **THEN** the summary SHALL only include lots matching workorder WO-001

#### Scenario: Matrix API with WIP filters
- **WHEN** `GET /api/hold-overview/matrix?hold_type=all&package=PKG-A`
- **THEN** the matrix SHALL only include lots matching package PKG-A

#### Scenario: Lots API with WIP filters
- **WHEN** `GET /api/hold-overview/lots?hold_type=quality&lotid=LOT-001`
- **THEN** the lot list SHALL only include lots matching LOT ID LOT-001

#### Scenario: Backward compatibility
- **WHEN** WIP filter parameters are omitted
- **THEN** the API SHALL behave identically to the current implementation (no filtering)
