## MODIFIED Requirements

### Requirement: Detail page SHALL receive drill-down parameters from Overview
The page SHALL initialize its state from two sources in priority order:
1. `loadWipNavigationState()` from sessionStorage (primary — used when arriving via drilldown)
2. URL query parameters (fallback — used for direct URL access or bookmarks)

The `workcenter` parameter SHALL always be read from the URL (it is always present and short).

#### Scenario: URL parameter initialization
- **WHEN** the page loads with `?workcenter={name}` in the URL
- **THEN** the page SHALL use the specified workcenter for data loading
- **THEN** the page title SHALL display "WIP Detail - {workcenter}"

#### Scenario: Filter passthrough from sessionStorage (primary path)
- **WHEN** the page loads with `?workcenter={name}` and `loadWipNavigationState()` returns stored filters
- **THEN** filter inputs SHALL be pre-filled with the sessionStorage values
- **THEN** data SHALL be loaded with those filters applied
- **THEN** the sessionStorage entry SHALL be consumed

#### Scenario: Filter passthrough from URL params (fallback path)
- **WHEN** the page loads with filter parameters in the URL and no sessionStorage state exists
- **THEN** filter inputs SHALL be pre-filled with URL parameter values
- **THEN** data SHALL be loaded with those filters applied

#### Scenario: Status passthrough from Overview
- **WHEN** the URL contains a `status` parameter (e.g., `?workcenter=焊接_DW&status=RUN`)
- **THEN** the status card corresponding to the `status` value SHALL be activated
- **THEN** data SHALL be loaded with the status filter applied

#### Scenario: Missing workcenter fallback
- **WHEN** the page loads without a `workcenter` parameter
- **THEN** the page SHALL fetch available workcenters from `GET /api/wip/meta/workcenters`
- **THEN** the first workcenter SHALL be used and the URL SHALL be updated via `replaceState`

### Requirement: Detail page SHALL have back navigation to Overview with filter preservation
The page SHALL provide a way to return to the Overview page while preserving all current filter state. The back action SHALL use SPA navigation (not `<a href>`).

#### Scenario: Back button with filter state
- **WHEN** user clicks the "← Overview" button in the header
- **THEN** the page SHALL call `storeWipNavigationState(filters, status)` to save current filter state
- **THEN** the page SHALL navigate via `navigateToRuntimeRoute('/wip-overview')` (no query params)
- **THEN** the navigation SHALL NOT trigger a full page load to the server

#### Scenario: Back button reflects Detail changes
- **WHEN** the user modifies filters or status in Detail (e.g., changes status from RUN to QUEUE)
- **THEN** the back action SHALL save the modified filter state to sessionStorage
- **THEN** navigating back SHALL cause Overview to load with the updated filter state

#### Scenario: Back navigation URL never exceeds server limit
- **WHEN** user clicks back with 100+ selected lotids and workorders
- **THEN** the navigation URL SHALL be `/wip-overview` (no query params — state is in sessionStorage)
- **THEN** no `400 Bad Request` error SHALL occur

### Requirement: Detail page SHALL synchronize status filter to URL
The page SHALL include the active status filter in URL state management. The length-guarded `replaceRuntimeHistory` SHALL automatically handle overflow.

#### Scenario: Status included in URL state
- **WHEN** a status filter is active and `updateUrlState()` runs
- **THEN** the URL SHALL include the `status` parameter
- **THEN** if the total URL exceeds 2000 chars, the guard SHALL spill to sessionStorage automatically
