## ADDED Requirements

### Requirement: Resource Status page SHALL display summary KPI cards
The page SHALL show 10 summary cards with aggregated equipment status statistics.

#### Scenario: Summary cards rendering
- **WHEN** equipment data is loaded from `GET /api/resource/status/summary`
- **THEN** 10 cards SHALL display: Total, PRD, SBY, UDT, SDT, EGT, NST, OTHER, OU%, Availability%
- **THEN** each status card SHALL show count and percentage
- **THEN** OU% card SHALL use color coding: green (≥80%), yellow (≥50%), red (<50%)

#### Scenario: Status card click filters equipment
- **WHEN** user clicks a status card (PRD, SBY, UDT, SDT, EGT, NST)
- **THEN** the equipment grid SHALL filter to show only equipment in that status
- **THEN** the clicked card SHALL show an active visual state
- **THEN** clicking the same card again SHALL remove the filter

### Requirement: Resource Status page SHALL display hierarchical matrix table
The page SHALL show a three-level expandable matrix of workcenter group, family, and resource with status columns.

#### Scenario: Matrix table rendering
- **WHEN** equipment data is loaded from `GET /api/resource/status`
- **THEN** a matrix table SHALL display with columns: Name, Total, PRD, SBY, UDT, SDT, EGT, NST, OTHER, OU%
- **THEN** Level 0 rows SHALL show workcenter groups with aggregated counts
- **THEN** Level 1 rows SHALL show resource families with aggregated counts
- **THEN** Level 2 rows SHALL show individual equipment with status indicator

#### Scenario: Status code aggregation
- **WHEN** equipment has status PM or BKD
- **THEN** the status SHALL be aggregated under UDT column
- **WHEN** equipment has status ENG
- **THEN** the status SHALL be aggregated under EGT column
- **WHEN** equipment has status OFF
- **THEN** the status SHALL be aggregated under NST column

#### Scenario: Tree expand and collapse
- **WHEN** user clicks the expand button on a Level 0 row
- **THEN** Level 1 rows (families) for that group SHALL toggle visibility
- **WHEN** user clicks the expand button on a Level 1 row
- **THEN** Level 2 rows (equipment) for that family SHALL toggle visibility
- **WHEN** user clicks "Expand All" or "Collapse All" in the toolbar
- **THEN** all tree rows SHALL expand or collapse accordingly

#### Scenario: Matrix cell click filters equipment
- **WHEN** user clicks a status count cell in the matrix (e.g., PRD count for a workcenter group)
- **THEN** the equipment grid SHALL filter to that workcenter group and status
- **THEN** the clicked cell SHALL show a selected visual state
- **THEN** a filter indicator banner SHALL display showing active filters
- **THEN** clicking the same cell again SHALL remove the filter

### Requirement: Resource Status page SHALL display equipment card grid
The page SHALL show filterable equipment cards with status information.

#### Scenario: Equipment card rendering
- **WHEN** equipment data is loaded
- **THEN** cards SHALL display in a responsive grid (auto-fill, min 280px)
- **THEN** each card SHALL show: resource name, status badge, workcenter, group, family, location
- **THEN** each card SHALL have a colored left border matching its status category

#### Scenario: LOT information tooltip
- **WHEN** user clicks the LOT count indicator on an equipment card
- **THEN** a floating tooltip SHALL display with LOT details: LOTID, QTY, track-in time, employee
- **THEN** the tooltip SHALL be positioned within the viewport (clamp to edges)
- **THEN** clicking outside the tooltip SHALL close it

#### Scenario: JOB information tooltip
- **WHEN** user clicks the JOB indicator on an equipment card
- **THEN** a floating tooltip SHALL display with JOB details: order, status, model, stage, technician, symptom/cause/repair codes
- **THEN** the tooltip SHALL use the same positioning logic as the LOT tooltip

### Requirement: Resource Status page SHALL support workcenter and equipment type filtering
The page SHALL provide filter controls to narrow the displayed equipment.

#### Scenario: Workcenter group filter
- **WHEN** user selects a workcenter group from the dropdown
- **THEN** all data (summary, matrix, equipment) SHALL reload filtered to that group
- **THEN** the dropdown options SHALL be loaded from `GET /api/resource/status/options`

#### Scenario: Equipment type checkboxes
- **WHEN** user toggles a checkbox (生產設備, 重點設備, 監控設備)
- **THEN** all data SHALL reload with the corresponding filter (is_production, is_key, is_monitor)
- **THEN** multiple checkboxes can be active simultaneously

### Requirement: Resource Status page SHALL display cache status
The page SHALL show the real-time cache health and last update time.

#### Scenario: Cache status indicator
- **WHEN** the page loads
- **THEN** the page SHALL call `GET /health` to check cache status
- **THEN** a green dot SHALL display when cache is loaded and enabled
- **THEN** a yellow dot SHALL display when cache is loading
- **THEN** a red dot SHALL display when cache is not enabled
- **THEN** the last update timestamp SHALL display from equipment status cache metadata

### Requirement: Resource Status page SHALL auto-refresh and handle request cancellation
The page SHALL automatically refresh data and prevent stale request pile-up.

#### Scenario: Auto-refresh interval
- **WHEN** the page is loaded
- **THEN** data SHALL auto-refresh every 5 minutes
- **THEN** auto-refresh SHALL be skipped when the tab is hidden

#### Scenario: Visibility change refresh
- **WHEN** the tab becomes visible after being hidden
- **THEN** data SHALL refresh immediately

#### Scenario: Manual refresh
- **WHEN** user clicks the refresh button
- **THEN** data SHALL reload and the auto-refresh timer SHALL reset

### Requirement: Resource Status page SHALL handle loading and error states
The page SHALL display appropriate feedback during API calls and on errors.

#### Scenario: Initial loading overlay
- **WHEN** the page first loads
- **THEN** a loading overlay SHALL display until all data is loaded

#### Scenario: API error handling
- **WHEN** an API call fails
- **THEN** the affected section SHALL display an error message
- **THEN** the page SHALL NOT crash or become unresponsive
