## Purpose
Define stable requirements for wip-overview-page.

## Requirements


### Requirement: Overview page SHALL display WIP summary statistics
The page SHALL fetch and display total lot count and total quantity as summary cards.

#### Scenario: Summary cards rendering
- **WHEN** the page loads
- **THEN** the page SHALL call `GET /api/wip/overview/summary`
- **THEN** summary cards SHALL display Total Lots and Total QTY with zh-TW number formatting
- **THEN** values SHALL animate with a scale transition when updated

#### Scenario: Data update timestamp
- **WHEN** summary data is loaded
- **THEN** the header SHALL display the `dataUpdateDate` from the API response

### Requirement: Overview page SHALL display WIP status breakdown cards
The page SHALL display four clickable status cards (RUN, QUEUE, 品質異常, 非品質異常) with lot and quantity counts.

#### Scenario: Status cards rendering
- **WHEN** summary data is loaded
- **THEN** four status cards SHALL be displayed with color coding (green=RUN, yellow=QUEUE, red=品質異常, orange=非品質異常)
- **THEN** each card SHALL show lot count and quantity

#### Scenario: Status card click filters matrix
- **WHEN** user clicks a status card
- **THEN** the matrix table SHALL reload with the selected status filter
- **THEN** the clicked card SHALL show an active visual state
- **THEN** non-active cards SHALL dim to 50% opacity
- **THEN** clicking the same card again SHALL deactivate the filter and restore all cards
- **THEN** the URL SHALL be updated to reflect the active status filter

### Requirement: Overview page SHALL display Workcenter × Package matrix
The page SHALL display a cross-tabulation table of workcenters vs packages.

#### Scenario: Matrix table rendering
- **WHEN** matrix data is loaded from `GET /api/wip/overview/matrix`
- **THEN** the table SHALL display workcenters as rows and packages as columns (limited to top 15)
- **THEN** the first column (Workcenter) SHALL be sticky on horizontal scroll
- **THEN** a Total row and Total column SHALL be displayed

#### Scenario: Matrix workcenter drill-down
- **WHEN** user clicks a workcenter name in the matrix
- **THEN** the page SHALL navigate to `/wip-detail?workcenter={name}`
- **THEN** active filter values (workorder, lotid, package, type) SHALL be passed as URL parameters
- **THEN** the active status filter SHALL be passed as the `status` URL parameter if set

### Requirement: Overview page SHALL display Hold Pareto analysis
The page SHALL display Pareto charts and tables for quality and non-quality hold reasons.

#### Scenario: Pareto chart rendering
- **WHEN** hold data is loaded from `GET /api/wip/overview/hold`
- **THEN** hold items SHALL be split into quality and non-quality groups
- **THEN** each group SHALL display an ECharts dual-axis Pareto chart (bar=QTY, line=cumulative %)
- **THEN** items SHALL be sorted by QTY descending

#### Scenario: Pareto chart drill-down
- **WHEN** user clicks a bar in the Pareto chart
- **THEN** the page SHALL navigate to `/hold-detail?reason={reason}`

#### Scenario: Pareto table with drill-down links
- **WHEN** Pareto data is rendered
- **THEN** a table SHALL display below each chart with Hold Reason, Lots, QTY, and cumulative %
- **THEN** reason names SHALL be clickable links to `/hold-detail?reason={reason}`

#### Scenario: Empty hold data
- **WHEN** a hold type has no items
- **THEN** the chart area SHALL display a "目前無資料" message
- **THEN** the chart SHALL be cleared

### Requirement: Overview page SHALL support autocomplete filtering
The page SHALL provide autocomplete-enabled filter inputs for WORKORDER, LOT ID, PACKAGE, and TYPE.

#### Scenario: Autocomplete search
- **WHEN** user types 2+ characters in a filter input
- **THEN** the page SHALL call `GET /api/wip/meta/search` with debounce (300ms)
- **THEN** suggestions SHALL appear in a dropdown below the input
- **THEN** cross-filter parameters SHALL be included (other active filter values)

#### Scenario: Apply and clear filters
- **WHEN** user clicks "套用篩選" or presses Enter in a filter input
- **THEN** all three API calls (summary, matrix, hold) SHALL reload with the filter values
- **THEN** the URL SHALL be updated to reflect the applied filter values
- **WHEN** user clicks "清除篩選"
- **THEN** all filter inputs SHALL be cleared and data SHALL reload without filters
- **THEN** the URL SHALL be cleared of all filter and status parameters

#### Scenario: Active filter display
- **WHEN** filters are applied
- **THEN** active filters SHALL be displayed as removable tags (e.g., "WO: {value} ×")
- **THEN** clicking a tag's remove button SHALL clear that filter, reload data, and update the URL

### Requirement: Overview page SHALL auto-refresh and handle request cancellation
The page SHALL automatically refresh data and prevent stale request pile-up.

#### Scenario: Auto-refresh interval
- **WHEN** the page is loaded
- **THEN** data SHALL auto-refresh every 10 minutes
- **THEN** auto-refresh SHALL be skipped when the tab is hidden (`document.hidden`)

#### Scenario: Visibility change refresh
- **WHEN** the tab becomes visible after being hidden
- **THEN** data SHALL refresh immediately

#### Scenario: Request cancellation
- **WHEN** a new data load is triggered while a previous request is in-flight
- **THEN** the previous request SHALL be cancelled via AbortController
- **THEN** the cancelled request SHALL NOT update the UI

#### Scenario: Manual refresh
- **WHEN** user clicks the "重新整理" button
- **THEN** data SHALL reload and the auto-refresh timer SHALL reset

### Requirement: Overview page SHALL persist filter state in URL
The page SHALL synchronize all filter state (workorder, lotid, package, type, status) to URL query parameters as the single source of truth.

#### Scenario: URL state initialization on page load
- **WHEN** the page loads with filter query parameters in the URL (e.g., `?package=SOD-323&status=RUN`)
- **THEN** the filter inputs SHALL be pre-filled with the URL parameter values
- **THEN** the status card corresponding to the `status` parameter SHALL be activated
- **THEN** data SHALL be loaded with all restored filters and status applied

#### Scenario: URL state initialization without parameters
- **WHEN** the page loads without any filter query parameters
- **THEN** all filters SHALL be empty and no status card SHALL be active
- **THEN** data SHALL load without filters (current default behavior)

#### Scenario: URL update on filter change
- **WHEN** filters are applied, cleared, or a single filter is removed
- **THEN** the URL SHALL be updated via `history.replaceState` to reflect the current filter state
- **THEN** only non-empty filter values SHALL appear as URL parameters

#### Scenario: URL update on status toggle
- **WHEN** a status card is clicked to activate or deactivate
- **THEN** the URL SHALL be updated via `history.replaceState` to include or remove the `status` parameter
