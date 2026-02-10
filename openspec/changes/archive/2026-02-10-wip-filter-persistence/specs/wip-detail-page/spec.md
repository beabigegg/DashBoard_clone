## MODIFIED Requirements

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

#### Scenario: Status passthrough from Overview
- **WHEN** the URL contains a `status` parameter (e.g., `?workcenter=焊接_DW&status=RUN`)
- **THEN** the status card corresponding to the `status` value SHALL be activated
- **THEN** data SHALL be loaded with the status filter applied

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
- **THEN** the URL SHALL be updated to reflect the active status filter

### Requirement: Detail page SHALL have back navigation to Overview with filter preservation
The page SHALL provide a way to return to the Overview page while preserving all current filter state.

#### Scenario: Back button with filter state
- **WHEN** user clicks the "← Overview" button in the header
- **THEN** the page SHALL navigate to `/wip-overview` with current filter values (workorder, lotid, package, type) and status as URL parameters
- **THEN** only non-empty filter values SHALL appear as URL parameters

#### Scenario: Back button reflects Detail changes
- **WHEN** the user modifies filters or status in Detail (e.g., changes status from RUN to QUEUE)
- **THEN** the back button URL SHALL dynamically update to reflect the current Detail filter state
- **THEN** navigating back SHALL cause Overview to load with the updated filter state

## ADDED Requirements

### Requirement: Detail page SHALL synchronize status filter to URL
The page SHALL include the active status filter in URL state management.

#### Scenario: Status included in URL state
- **WHEN** the status filter is active
- **THEN** `updateUrlState()` SHALL include `status={value}` in the URL parameters
- **WHEN** the status filter is cleared
- **THEN** the `status` parameter SHALL be removed from the URL
