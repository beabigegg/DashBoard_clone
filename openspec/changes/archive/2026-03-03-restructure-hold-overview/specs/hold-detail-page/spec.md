## MODIFIED Requirements

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
