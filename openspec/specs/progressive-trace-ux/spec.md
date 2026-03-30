## Purpose
Define stable requirements for progressive-trace-ux.

## Requirements

### Requirement: query-tool lineage tab SHALL load on-demand
The query-tool lineage tree SHALL auto-fire lineage API calls after lot resolution with concurrency-limited parallel requests and progressive rendering, while preserving on-demand expand/collapse for tree navigation.

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

### Requirement: Trace stage timeout
The `useTraceProgress` composable's `DEFAULT_STAGE_TIMEOUT_MS` SHALL be 360000 (360 seconds) to accommodate large-scale trace operations.

#### Scenario: Large trace operation completes
- **WHEN** a trace stage (seed-resolve, lineage, or events) takes up to 300 seconds
- **THEN** the frontend does not abort the stage request

### Requirement: MSD detail calls SHALL include trace_query_id
The MSD App.vue `buildDetailParams()` function SHALL include the `trace_query_id` captured from the events stage result when available, so the backend can locate the correct DuckDB spool file.

#### Scenario: Detail load after successful trace pipeline
- **WHEN** the trace pipeline completes seed→lineage→events and `currentTraceQueryId` is set
- **THEN** `loadDetail()` SHALL send `trace_query_id` as a query parameter to `/api/mid-section-defect/analysis/detail`
- **THEN** the backend SHALL use the spool file matching `trace_query_id` to serve paginated detail data

#### Scenario: Detail load when currentTraceQueryId is null
- **WHEN** `currentTraceQueryId` is null (events stage failed or was skipped)
- **THEN** `loadDetail()` SHALL omit `trace_query_id` from the request
- **THEN** the backend SHALL resolve context from date/station/direction params as before
