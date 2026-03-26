## MODIFIED Requirements

### Requirement: Overview page SHALL support dropdown filtering
The page SHALL provide searchable dropdown filters for WORKORDER, LOT ID, PACKAGE, TYPE, Wafer LOT, and Wafer Type.

#### Scenario: Filter options preload from cache-backed endpoint
- **WHEN** the page initializes
- **THEN** the page SHALL call `GET /api/wip/meta/filter-options`
- **THEN** dropdown options SHALL be loaded before user performs first query
- **THEN** options SHALL include `workorders`, `lotids`, `packages`, `types`, `firstnames`, and `waferdescs`

#### Scenario: Searchable dropdown interaction
- **WHEN** user opens any filter dropdown
- **THEN** the dropdown SHALL support fuzzy keyword search over loaded options
- **THEN** user SHALL be able to select one or multiple options

#### Scenario: Apply and clear filters
- **WHEN** user clicks `套用篩選`
- **THEN** all three API calls (`/api/wip/overview/summary`, `/api/wip/overview/matrix`, `/api/wip/overview/hold`) SHALL reload with selected filter values
- **WHEN** user clicks `清除篩選`
- **THEN** all filter values SHALL reset and data SHALL reload without filters

#### Scenario: Active filter chips
- **WHEN** any filter has selected values
- **THEN** selected values SHALL be displayed as removable chips
- **THEN** removing a chip SHALL trigger data reload with updated filters

### Requirement: Overview page SHALL persist filter state in URL
The page SHALL synchronize all filter state to URL query parameters as the single source of truth.

#### Scenario: URL state includes new wafer filters
- **WHEN** filters are applied
- **THEN** URL query parameters SHALL include non-empty values for `workorder`, `lotid`, `package`, `type`, `firstname`, `waferdesc`, and `status`
- **THEN** multi-select values SHALL be serialized as comma-separated strings

#### Scenario: URL state restoration on load
- **WHEN** the page is loaded with filter query parameters
- **THEN** all filter controls SHALL restore values from URL
- **THEN** data SHALL load with restored filters applied
