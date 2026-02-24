## MODIFIED Requirements

### Requirement: query-tool lineage tab SHALL load on-demand
The query-tool lineage tree SHALL auto-fire lineage API calls after lot resolution with concurrency-limited parallel requests and progressive rendering, while preserving on-demand expand/collapse for tree navigation.

The mid_section_defect profile SHALL support a `direction` parameter that controls lineage resolution direction: `backward` uses `resolve_full_genealogy()` (ancestors), `forward` uses `resolve_forward_tree()` (descendants).

`useTraceProgress.js` `PROFILE_DOMAINS` for `mid_section_defect` SHALL include `'upstream_history'` for backward and `['upstream_history', 'downstream_rejects']` for forward. Domain selection SHALL be handled by the backend based on `direction` in params.

`collectAllContainerIds()` SHALL support forward direction by collecting descendants from `children_map` (instead of ancestors) when `direction='forward'` is present in params.

#### Scenario: Auto-fire lineage after resolve
- **WHEN** lot resolution completes with N resolved lots
- **THEN** lineage SHALL be fetched via `POST /api/trace/lineage` for each lot automatically
- **THEN** concurrent requests SHALL be limited to 3 at a time to respect rate limits (10/60s)
- **THEN** response time SHALL be ≤3s per individual lot

#### Scenario: Multiple lots lineage results cached
- **WHEN** lineage data has been fetched for multiple lots
- **THEN** each lot's lineage data SHALL be preserved independently (not re-fetched)
- **WHEN** a new resolve query is executed
- **THEN** all cached lineage data SHALL be cleared

#### Scenario: Mid-section defect backward lineage
- **WHEN** profile is `mid_section_defect` and direction is `backward`
- **THEN** lineage stage SHALL call `resolve_full_genealogy()` to get ancestor container IDs
- **THEN** `collectAllContainerIds()` SHALL merge seed IDs with ancestor IDs

#### Scenario: Mid-section defect forward lineage
- **WHEN** profile is `mid_section_defect` and direction is `forward`
- **THEN** lineage stage SHALL call `resolve_forward_tree()` to get descendant container IDs
- **THEN** `collectAllContainerIds()` SHALL merge seed IDs with descendant IDs from `children_map`
