## Purpose
Define stable requirements for hold-detail-page.

## Requirements


### Requirement: Hold Detail page SHALL display hold reason analysis
The page SHALL show summary statistics for a specific hold reason.

#### Scenario: Summary cards rendering
- **WHEN** the page loads with `?reason={reason}` in the URL
- **THEN** the page SHALL call `GET /api/wip/hold-detail/summary` with the reason
- **THEN** five cards SHALL display: Total Lots, Total QTY, 平均當站滯留, 最久當站滯留, 影響站群
- **THEN** age values SHALL display with "天" suffix

#### Scenario: Hold type classification
- **WHEN** the page loads
- **THEN** the header gradient color SHALL be red (#ef4444) for quality holds or orange (#f97316) for non-quality holds
- **THEN** a badge SHALL display "品質異常" or "非品質異常" accordingly
- **THEN** classification SHALL use a frontend `NON_QUALITY_HOLD_REASONS` constant set (11 values matching backend `sql/filters.py`)

#### Scenario: Missing reason parameter
- **WHEN** the page loads without a `reason` URL parameter
- **THEN** the page SHALL redirect to `/hold-overview`

### Requirement: Hold Detail page SHALL display age distribution
The page SHALL show the distribution of hold lots by age at current station.

#### Scenario: Age distribution cards
- **WHEN** distribution data is loaded from `GET /api/wip/hold-detail/distribution`
- **THEN** four clickable cards SHALL display: 0-1天, 1-3天, 3-7天, 7+天
- **THEN** each card SHALL show Lots, QTY, and percentage

#### Scenario: Age card click filters lots
- **WHEN** user clicks an age card
- **THEN** the lot table SHALL reload filtered to that age range
- **THEN** the clicked card SHALL show a blue active border
- **THEN** clicking the same card again SHALL remove the filter

### Requirement: Hold Detail page SHALL display workcenter and package distribution
The page SHALL show distribution tables for workcenter and package breakdowns.

#### Scenario: Distribution tables rendering
- **WHEN** distribution data is loaded
- **THEN** two side-by-side tables SHALL display: By Workcenter and By Package
- **THEN** each table SHALL show Name, Lots, QTY, and percentage columns
- **THEN** tables SHALL be scrollable with max-height 300px

#### Scenario: Distribution row click filters lots
- **WHEN** user clicks a row in the workcenter or package table
- **THEN** the lot table SHALL reload filtered by that workcenter or package
- **THEN** the clicked row SHALL show an active highlight
- **THEN** clicking the same row again SHALL remove the filter

### Requirement: Hold Detail page SHALL display paginated lot details
The page SHALL display detailed lot information with server-side pagination.

#### Scenario: Lot table rendering
- **WHEN** lot data is loaded from `GET /api/wip/hold-detail/lots`
- **THEN** a table SHALL display with 13 columns: LOTID, WORKORDER, QTY, Product, Package, Workcenter, Hold Reason, Spec, Age, Hold By, Dept, Hold Comment, Future Hold Comment
- **THEN** age values SHALL display with "天" suffix

#### Scenario: Filter indicator
- **WHEN** any filter is active (workcenter, package, or age range)
- **THEN** a blue filter indicator bar SHALL display showing active filters (e.g., "篩選: Workcenter=WC-A, Age=3-7天")
- **THEN** clicking the "×" on the indicator SHALL clear all filters

#### Scenario: Pagination
- **WHEN** total pages exceeds 1
- **THEN** Prev/Next buttons and page info SHALL display
- **THEN** page info SHALL show "顯示 {start} - {end} / {total}"

#### Scenario: Filter changes reset pagination
- **WHEN** any filter is toggled
- **THEN** pagination SHALL reset to page 1

### Requirement: Hold Detail page SHALL have back navigation to Hold Overview
The page SHALL provide a way to return to the Hold Overview page.

#### Scenario: Back button
- **WHEN** user clicks the "← Hold Overview" button in the header
- **THEN** the page SHALL navigate to `/hold-overview`

### Requirement: Hold Detail page SHALL auto-refresh and handle request cancellation
The page SHALL automatically refresh data and prevent stale request pile-up.

#### Scenario: Auto-refresh interval
- **WHEN** the page is loaded
- **THEN** data SHALL auto-refresh every 10 minutes
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
- **THEN** data SHALL reload and the auto-refresh timer SHALL reset

### Requirement: Hold Detail page SHALL handle loading and error states
The page SHALL display appropriate feedback during API calls and on errors.

#### Scenario: Initial loading overlay
- **WHEN** the page first loads
- **THEN** a full-page loading overlay SHALL display until all data is loaded

#### Scenario: API error handling
- **WHEN** an API call fails
- **THEN** the affected section SHALL display an error message
- **THEN** the page SHALL NOT crash or become unresponsive

#### Scenario: Empty lot result
- **WHEN** a query returns zero lots
- **THEN** the lot table SHALL display a "No data" placeholder
