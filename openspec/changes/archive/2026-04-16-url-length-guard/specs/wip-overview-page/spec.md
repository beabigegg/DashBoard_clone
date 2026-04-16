## MODIFIED Requirements

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
