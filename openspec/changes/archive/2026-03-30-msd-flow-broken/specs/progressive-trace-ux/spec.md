## ADDED Requirements

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
