## ADDED Requirements

### Requirement: Hold Overview page SHALL display a filter bar with Hold Type and Reason
The page SHALL provide a filter bar for selecting hold type and hold reason.

#### Scenario: Hold Type radio default
- **WHEN** the page loads
- **THEN** the Hold Type filter SHALL default to "品質異常"
- **THEN** three radio options SHALL display: 品質異常, 非品質異常, 全部

#### Scenario: Hold Type change reloads all data
- **WHEN** user changes the Hold Type selection
- **THEN** all four API calls (summary, matrix, treemap, lots) SHALL reload with the new hold_type parameter
- **THEN** any active matrix and treemap filters SHALL be cleared

#### Scenario: Reason dropdown populated from current data
- **WHEN** summary data is loaded
- **THEN** the Reason dropdown SHALL display "全部" plus all distinct hold reasons from the treemap data
- **THEN** selecting a specific reason SHALL reload all four API calls filtered by that reason
- **THEN** any active matrix and treemap filters SHALL be cleared

### Requirement: Hold Overview page SHALL display summary KPI cards
The page SHALL show summary statistics for all hold lots matching the current filter.

#### Scenario: Summary cards rendering
- **WHEN** summary data is loaded from `GET /api/hold-overview/summary`
- **THEN** five cards SHALL display: Hold Lots, Hold QTY, 站別數, 平均滯留天數, 最大滯留天數
- **THEN** lot and QTY values SHALL use zh-TW number formatting
- **THEN** age values SHALL display with "天" suffix and one decimal place

#### Scenario: Summary reflects filter bar only
- **WHEN** user clicks a matrix cell or treemap block
- **THEN** summary cards SHALL NOT change (they only respond to filter bar changes)

### Requirement: Hold Overview page SHALL display a Workcenter x Package matrix
The page SHALL display a cross-tabulation matrix of workcenters vs packages for hold lots.

#### Scenario: Matrix table rendering
- **WHEN** matrix data is loaded from `GET /api/hold-overview/matrix`
- **THEN** the table SHALL display workcenters as rows and packages as columns
- **THEN** cell values SHALL show QTY with zh-TW number formatting
- **THEN** the first column (Workcenter) SHALL be sticky on horizontal scroll
- **THEN** a Total row and Total column SHALL be displayed
- **THEN** cells with zero value SHALL display "-"

#### Scenario: Matrix cell click filters TreeMap and lot table
- **WHEN** user clicks a QTY cell in the matrix (intersection of workcenter and package)
- **THEN** `matrixFilter` SHALL be set to `{ workcenter, package }`
- **THEN** TreeMap SHALL reload showing only data for that workcenter + package combination
- **THEN** lot table SHALL reload filtered by that workcenter + package
- **THEN** the clicked cell SHALL show an active highlight

#### Scenario: Matrix workcenter row click
- **WHEN** user clicks a workcenter name or its Total cell
- **THEN** `matrixFilter` SHALL be set to `{ workcenter }` (all packages)
- **THEN** TreeMap and lot table SHALL reload filtered by that workcenter

#### Scenario: Matrix package column click
- **WHEN** user clicks a package column header or its Total cell
- **THEN** `matrixFilter` SHALL be set to `{ package }` (all workcenters)
- **THEN** TreeMap and lot table SHALL reload filtered by that package

#### Scenario: Matrix click toggle
- **WHEN** user clicks the same cell/row/column that is already active
- **THEN** `matrixFilter` SHALL be cleared
- **THEN** TreeMap and lot table SHALL reload without matrix filter

#### Scenario: Matrix reflects filter bar only
- **WHEN** user clicks a treemap block
- **THEN** matrix SHALL NOT change (it only responds to filter bar changes)

### Requirement: Hold Overview page SHALL display active filter indicators
The page SHALL show a clear indicator of active cascade filters.

#### Scenario: Matrix filter indicator
- **WHEN** a matrix filter is active
- **THEN** a filter indicator SHALL display between the matrix and TreeMap sections
- **THEN** the indicator SHALL show the active workcenter and/or package name
- **THEN** a clear button (✕) SHALL remove the matrix filter

#### Scenario: TreeMap filter indicator
- **WHEN** a treemap filter is active
- **THEN** a filter indicator SHALL display between the TreeMap and lot table sections
- **THEN** the indicator SHALL show the active workcenter and reason name
- **THEN** a clear button (✕) SHALL remove the treemap filter

#### Scenario: Clear all filters
- **WHEN** user clicks a "清除所有篩選" button
- **THEN** both matrixFilter and treemapFilter SHALL be cleared
- **THEN** TreeMap and lot table SHALL reload without cascade filters

### Requirement: Hold Overview page SHALL display a TreeMap visualization
The page SHALL display a TreeMap chart showing hold lot distribution by workcenter and reason.

#### Scenario: TreeMap rendering
- **WHEN** treemap data is loaded from `GET /api/hold-overview/treemap`
- **THEN** the TreeMap SHALL display with two levels: Workcenter (parent) → Hold Reason (child)
- **THEN** block area SHALL represent QTY
- **THEN** block color SHALL represent average age at current station using a 4-level color scale
- **THEN** the color scale legend SHALL display: 綠(<1天), 黃(1-3天), 橙(3-7天), 紅(>7天)

#### Scenario: TreeMap tooltip
- **WHEN** user hovers over a TreeMap block
- **THEN** a tooltip SHALL display: Workcenter, Reason, Lots count, QTY, and average age

#### Scenario: TreeMap narrows on matrix filter (Option A)
- **WHEN** a matrix filter is active (e.g., workcenter=WC-MOLD, package=PKG-A)
- **THEN** the TreeMap SHALL only show data matching the matrix filter
- **THEN** the TreeMap API SHALL be called with workcenter and/or package parameters

#### Scenario: TreeMap click filters lot table
- **WHEN** user clicks a leaf block in the TreeMap (a specific reason within a workcenter)
- **THEN** `treemapFilter` SHALL be set to `{ workcenter, reason }`
- **THEN** lot table SHALL reload filtered by that workcenter + reason
- **THEN** the clicked block SHALL show a visual highlight (border or opacity change)

#### Scenario: TreeMap click toggle
- **WHEN** user clicks the same block that is already active
- **THEN** `treemapFilter` SHALL be cleared
- **THEN** lot table SHALL reload without treemap filter

#### Scenario: Empty TreeMap
- **WHEN** treemap data returns zero items
- **THEN** the TreeMap area SHALL display "目前無 Hold 資料"

### Requirement: Hold Overview page SHALL display paginated lot details
The page SHALL display a detailed lot table with server-side pagination.

#### Scenario: Lot table rendering
- **WHEN** lot data is loaded from `GET /api/hold-overview/lots`
- **THEN** a table SHALL display with columns: LOTID, WORKORDER, QTY, Package, Workcenter, Hold Reason, Age, Hold By, Dept, Hold Comment
- **THEN** age values SHALL display with "天" suffix

#### Scenario: Lot table responds to all cascade filters
- **WHEN** matrixFilter is `{ workcenter: WC-A, package: PKG-1 }` and treemapFilter is `{ reason: 品質確認 }`
- **THEN** lots API SHALL be called with `workcenter=WC-A&package=PKG-1&treemap_reason=品質確認`
- **THEN** only lots matching all active filters SHALL be displayed

#### Scenario: Pagination
- **WHEN** total lots exceeds per_page (50)
- **THEN** Prev/Next buttons and page info SHALL display
- **THEN** page info SHALL show "顯示 {start} - {end} / {total}"

#### Scenario: Filter changes reset pagination
- **WHEN** any filter changes (filter bar, matrix click, or treemap click)
- **THEN** pagination SHALL reset to page 1

#### Scenario: Empty lot result
- **WHEN** a query returns zero lots
- **THEN** the lot table SHALL display a "No data" placeholder

### Requirement: Hold Overview page SHALL auto-refresh and handle request cancellation
The page SHALL automatically refresh data and prevent stale request pile-up.

#### Scenario: Auto-refresh interval
- **WHEN** the page is loaded
- **THEN** data SHALL auto-refresh every 10 minutes using `useAutoRefresh` composable
- **THEN** auto-refresh SHALL be skipped when the tab is hidden

#### Scenario: Visibility change refresh
- **WHEN** the tab becomes visible after being hidden
- **THEN** data SHALL refresh immediately

#### Scenario: Request cancellation
- **WHEN** a new data load is triggered while a previous request is in-flight
- **THEN** the previous request SHALL be cancelled via AbortController
- **THEN** the cancelled request SHALL NOT update the UI

#### Scenario: Manual refresh
- **WHEN** user clicks the "重新整理" button
- **THEN** all data SHALL reload and the auto-refresh timer SHALL reset
- **THEN** all cascade filters (matrixFilter, treemapFilter) SHALL be preserved during refresh

### Requirement: Hold Overview page SHALL handle loading and error states
The page SHALL display appropriate feedback during API calls and on errors.

#### Scenario: Initial loading overlay
- **WHEN** the page first loads
- **THEN** a full-page loading overlay SHALL display until all data is loaded

#### Scenario: API error handling
- **WHEN** an API call fails
- **THEN** an error banner SHALL display with the error message
- **THEN** the page SHALL NOT crash or become unresponsive

#### Scenario: Refresh indicator
- **WHEN** data is being refreshed (not initial load)
- **THEN** a spinning refresh indicator SHALL display in the header
- **THEN** a success checkmark SHALL flash briefly on completion

### Requirement: Hold Overview page SHALL have back navigation
The page SHALL provide navigation back to WIP Overview.

#### Scenario: Back button
- **WHEN** user clicks the "← WIP Overview" button in the header
- **THEN** the page SHALL navigate to `/wip-overview`
