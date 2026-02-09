## Purpose
Define stable requirements for wip-detail-page.

## Requirements


### Requirement: Detail page SHALL receive drill-down parameters from Overview
The page SHALL read URL query parameters to initialize its state from the Overview page drill-down.

#### Scenario: URL parameter initialization
- **WHEN** the page loads with `?workcenter={name}` in the URL
- **THEN** the page SHALL use the specified workcenter for data loading
- **THEN** the page title SHALL display "WIP Detail - {workcenter}"

#### Scenario: Filter passthrough from Overview
- **WHEN** the URL contains additional filter parameters (workorder, lotid, package, type)
- **THEN** filter inputs SHALL be pre-filled with those values
- **THEN** data SHALL be loaded with those filters applied

#### Scenario: Missing workcenter fallback
- **WHEN** the page loads without a `workcenter` parameter
- **THEN** the page SHALL fetch available workcenters from `GET /api/wip/meta/workcenters`
- **THEN** the first workcenter SHALL be used and the URL SHALL be updated via `replaceState`

### Requirement: Detail page SHALL display WIP summary cards
The page SHALL display five summary cards with status counts for the current workcenter.

#### Scenario: Summary cards rendering
- **WHEN** detail data is loaded
- **THEN** five cards SHALL display: Total Lots, RUN, QUEUE, 品質異常, 非品質異常

#### Scenario: Status card click filters table
- **WHEN** user clicks a status card (RUN, QUEUE, 品質異常, 非品質異常)
- **THEN** the lot table SHALL reload filtered to that status
- **THEN** the active card SHALL show a visual active state
- **THEN** non-active status cards SHALL dim
- **THEN** clicking the same card again SHALL remove the filter

### Requirement: Detail page SHALL display lot details table with sticky columns
The page SHALL display a scrollable table with fixed left columns and dynamic spec columns.

#### Scenario: Table with sticky columns
- **WHEN** lot data is loaded from `GET /api/wip/detail/{workcenter}`
- **THEN** the table SHALL display with 4 sticky left columns: LOT ID, Equipment, WIP Status, Package
- **THEN** dynamic spec columns (e.g., 1OO, 2OO, TC) SHALL render to the right
- **THEN** the sticky columns SHALL remain visible during horizontal scroll

#### Scenario: LOT ID is clickable
- **WHEN** user clicks a LOT ID in the table
- **THEN** the lot detail panel SHALL open below the table
- **THEN** the clicked LOT ID SHALL show an active highlight

#### Scenario: WIP Status display
- **WHEN** a lot has status HOLD
- **THEN** the status cell SHALL display "HOLD ({holdReason})" with red styling
- **WHEN** a lot has status RUN or QUEUE
- **THEN** the status cell SHALL display with green or yellow styling respectively

#### Scenario: Spec column data display
- **WHEN** a lot's spec matches a spec column
- **THEN** the cell SHALL display the lot QTY with green background
- **THEN** non-matching spec cells SHALL be empty

### Requirement: Detail page SHALL display inline lot detail panel
The page SHALL show expandable lot detail information when a LOT ID is clicked.

#### Scenario: Lot detail loading
- **WHEN** user clicks a LOT ID
- **THEN** the panel SHALL call `GET /api/wip/lot/{lotid}`
- **THEN** a loading indicator SHALL display while fetching

#### Scenario: Lot detail sections
- **WHEN** lot detail data is loaded
- **THEN** the panel SHALL display sections: 基本資訊, 產品資訊, 製程資訊, 物料資訊
- **THEN** Hold 資訊 section SHALL display only when status is HOLD or holdCount > 0
- **THEN** NCR 資訊 section SHALL display only when ncrId exists

#### Scenario: Close lot detail
- **WHEN** user clicks the Close button on the panel
- **THEN** the panel SHALL be hidden
- **THEN** the LOT ID highlight SHALL be removed

### Requirement: Detail page SHALL support autocomplete filtering
The page SHALL provide autocomplete-enabled filter inputs identical to Overview.

#### Scenario: Autocomplete with cross-filtering
- **WHEN** user types 2+ characters in a filter input
- **THEN** the page SHALL call `GET /api/wip/meta/search` with debounce (300ms)
- **THEN** cross-filter parameters SHALL be included
- **THEN** suggestions SHALL appear in a dropdown

#### Scenario: Apply filters resets pagination
- **WHEN** user applies filters
- **THEN** pagination SHALL reset to page 1
- **THEN** table data SHALL reload with the new filters

### Requirement: Detail page SHALL support server-side pagination
The page SHALL paginate lot data with server-side support.

#### Scenario: Pagination controls
- **WHEN** total pages exceeds 1
- **THEN** Prev/Next buttons and page info SHALL display
- **THEN** Prev SHALL be disabled on page 1
- **THEN** Next SHALL be disabled on the last page

#### Scenario: Page navigation
- **WHEN** user clicks Next or Prev
- **THEN** data SHALL reload with the updated page number

### Requirement: Detail page SHALL have back navigation to Overview
The page SHALL provide a way to return to the Overview page.

#### Scenario: Back button
- **WHEN** user clicks the "← Overview" button in the header
- **THEN** the page SHALL navigate to `/wip-overview`

### Requirement: Detail page SHALL auto-refresh and handle request cancellation
The page SHALL auto-refresh and cancel stale requests identically to Overview.

#### Scenario: Auto-refresh and cancellation
- **WHEN** the page is loaded
- **THEN** data SHALL auto-refresh every 10 minutes, skipping when tab is hidden
- **THEN** visibility change SHALL trigger immediate refresh
- **THEN** new requests SHALL cancel in-flight requests via AbortController
