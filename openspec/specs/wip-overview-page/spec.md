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

#### Scenario: RUN/QUEUE card click filters matrix
- **WHEN** user clicks the RUN or QUEUE status card
- **THEN** the matrix table SHALL reload with the selected status filter
- **THEN** the clicked card SHALL show an active visual state
- **THEN** clicking the same card again SHALL deactivate the filter and restore all cards
- **THEN** the URL SHALL be updated to reflect the active status filter

#### Scenario: Hold card click navigates to Hold Overview
- **WHEN** user clicks the "品質異常" status card
- **THEN** the page SHALL navigate to `/hold-overview?hold_type=quality`
- **WHEN** user clicks the "非品質異常" status card
- **THEN** the page SHALL navigate to `/hold-overview?hold_type=non-quality`

### Requirement: Overview page SHALL display Workcenter × Package matrix
The page SHALL display a cross-tabulation table of workcenters vs packages.

#### Scenario: Matrix table rendering
- **WHEN** matrix data is loaded from `GET /api/wip/overview/matrix`
- **THEN** the table SHALL display workcenters as rows and packages as columns (limited to top 15)
- **THEN** the first column (Workcenter) SHALL be sticky on horizontal scroll
- **THEN** a Total row and Total column SHALL be displayed

#### Scenario: Matrix workcenter drill-down
- **WHEN** user clicks a workcenter name in the matrix
- **THEN** the page SHALL call `storeWipNavigationState(filters, status)` before navigation
- **THEN** the page SHALL navigate to `/wip-detail?workcenter={name}` (plus `&status={status}` if active)
- **THEN** filter values SHALL be transferred via sessionStorage, not URL parameters

### Requirement: Overview page SHALL support autocomplete filtering
The page SHALL provide autocomplete-enabled filter inputs for WORKORDER, LOT ID, PACKAGE, and TYPE. Filter values selected from the dropdown list SHALL be matched against the dataset using **exact match** (case-insensitive). Fuzzy/substring search SHALL only occur at the autocomplete suggestion stage (UI layer, via `/api/wip/meta/search`); once values are applied as filters, only rows with exact field values SHALL appear in results.

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

#### Scenario: LOTID exact match returns only precise results
- **WHEN** user selects `LOT-123` from the LOTID filter dropdown and applies filters
- **THEN** the summary and matrix SHALL only include lots where `LOTID` exactly equals `LOT-123`
- **THEN** lots with LOTID `LOT-1234`, `XLOT-123`, or any other partial match SHALL NOT appear

#### Scenario: WORKORDER exact match returns only precise results
- **WHEN** user selects `WO001` from the WORKORDER filter dropdown and applies filters
- **THEN** results SHALL only include lots where `WORKORDER` exactly equals `WO001`

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
The page SHALL synchronize all filter state (workorder, lotid, package, type, firstname, waferdesc, status) to URL query parameters via `replaceRuntimeHistory`. The length-guarded `replaceRuntimeHistory` SHALL automatically spill to sessionStorage when the URL exceeds the safe threshold. No page-level code change is needed for this — the guard is transparent.

When navigating to wip-detail via matrix drilldown, the page SHALL store the current filter state in sessionStorage via `storeWipNavigationState` and navigate with only `?workcenter={name}` (plus `&status={status}` if active) in the URL. This ensures the destination URL never exceeds the server limit regardless of filter set size.

When loading with filters present in sessionStorage (returning from wip-detail), the page SHALL read from `loadWipNavigationState()` first, then fall back to URL params.

#### Scenario: URL state initialization on page load
- **WHEN** the page loads with filter query parameters in the URL (e.g., `?package=SOD-323&status=RUN`)
- **THEN** the filter inputs SHALL be pre-filled with the URL parameter values
- **THEN** the status card corresponding to the `status` parameter SHALL be activated
- **THEN** data SHALL be loaded with all restored filters and status applied

#### Scenario: URL state initialization without parameters
- **WHEN** the page loads without any filter query parameters
- **THEN** all filters SHALL be empty and no status card SHALL be active
- **THEN** data SHALL load without filters (current default behavior)

#### Scenario: URL state initialization from sessionStorage (returning from detail)
- **WHEN** the page loads without URL filter params but `loadWipNavigationState()` returns a stored state
- **THEN** filter inputs SHALL be pre-filled from the sessionStorage state
- **THEN** data SHALL be loaded with all restored filters applied

#### Scenario: URL update on filter change
- **WHEN** filters are applied, cleared, or a single filter is removed
- **THEN** the URL SHALL be updated via `replaceRuntimeHistory` to reflect the current filter state
- **THEN** only non-empty filter values SHALL appear as URL parameters
- **THEN** if the URL would exceed 2000 chars, the guard SHALL spill to sessionStorage automatically

#### Scenario: URL update on status toggle
- **WHEN** a status card is clicked to activate or deactivate
- **THEN** the URL SHALL be updated via `replaceRuntimeHistory` to include or remove the `status` parameter

#### Scenario: Drilldown to detail with large filter set
- **WHEN** user clicks a matrix cell to drill down to wip-detail with 50+ selected lotids
- **THEN** the page SHALL call `storeWipNavigationState(filters, status)` before navigation
- **THEN** the navigation URL SHALL be `/wip-detail?workcenter={name}` (plus `&status={status}` if active)
- **THEN** the URL length SHALL NOT exceed 200 characters regardless of filter count
