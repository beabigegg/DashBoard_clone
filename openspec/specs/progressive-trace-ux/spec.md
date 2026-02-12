## ADDED Requirements

### Requirement: useTraceProgress composable SHALL orchestrate staged fetching with reactive state
`useTraceProgress` SHALL provide a shared composable for sequential stage fetching with per-stage reactive state updates.

#### Scenario: Normal three-stage fetch sequence
- **WHEN** `useTraceProgress` is invoked with profile and params
- **THEN** it SHALL execute seed-resolve → lineage → events sequentially
- **THEN** after each stage completes, `current_stage` and `completed_stages` reactive refs SHALL update immediately
- **THEN** `stage_results` SHALL accumulate results from completed stages

#### Scenario: Stage failure does not block completed results
- **WHEN** the lineage stage fails after seed-resolve has completed
- **THEN** seed-resolve results SHALL remain visible and accessible
- **THEN** the error SHALL be captured in stage-specific error state
- **THEN** subsequent stages (events) SHALL NOT execute

### Requirement: mid-section-defect SHALL render progressively as stages complete
The mid-section-defect page SHALL display partial results as each trace stage completes.

#### Scenario: Seed lots visible before lineage completes
- **WHEN** seed-resolve stage completes (≤3s for ≥10 seed lots)
- **THEN** the seed lots list SHALL be rendered immediately
- **THEN** lineage and events sections SHALL show skeleton placeholders

#### Scenario: KPI/charts visible after events complete
- **WHEN** lineage and events stages complete
- **THEN** KPI cards and charts SHALL render with fade-in animation
- **THEN** no layout shift SHALL occur (skeleton placeholders SHALL have matching dimensions)

#### Scenario: Detail table pagination unchanged
- **WHEN** the user requests detail data
- **THEN** the existing detail endpoint with pagination SHALL be used (not the staged API)

### Requirement: query-tool lineage tab SHALL load on-demand
The query-tool lineage tab SHALL load lineage data for individual lots on user interaction, not batch-load all lots.

#### Scenario: User clicks a lot to view lineage
- **WHEN** the user clicks a lot card to expand lineage information
- **THEN** lineage SHALL be fetched via `/api/trace/lineage` for that single lot's container IDs
- **THEN** response time SHALL be ≤3s for the individual lot

#### Scenario: Multiple lots expanded
- **WHEN** the user expands lineage for multiple lots
- **THEN** each lot's lineage SHALL be fetched independently (not batch)
- **THEN** already-fetched lineage data SHALL be preserved (not re-fetched)

### Requirement: Both pages SHALL display a stage progress indicator
Both mid-section-defect and query-tool SHALL display a progress indicator showing the current trace stage.

#### Scenario: Progress indicator during staged fetch
- **WHEN** a trace query is in progress
- **THEN** a progress indicator SHALL display the current stage (seed → lineage → events)
- **THEN** completed stages SHALL be visually distinct from pending/active stages
- **THEN** the indicator SHALL replace the existing single loading spinner

### Requirement: Legacy static query-tool.js SHALL be removed
The pre-Vite static file `src/mes_dashboard/static/js/query-tool.js` (3056L, 126KB) SHALL be deleted as dead code.

#### Scenario: Dead code removal verification
- **WHEN** `static/js/query-tool.js` is deleted
- **THEN** grep for `static/js/query-tool.js` SHALL return zero results across the codebase
- **THEN** `query_tool.html` template SHALL continue to function via `frontend_asset('query-tool.js')` which resolves to the Vite-built bundle
- **THEN** `frontend/src/query-tool/main.js` (Vue 3 Vite entry) SHALL remain unaffected
