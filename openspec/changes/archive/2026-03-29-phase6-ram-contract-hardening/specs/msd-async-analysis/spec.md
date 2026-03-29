## MODIFIED Requirements

### Requirement: MSD detail endpoint SHALL use a canonical spool identifier
`GET /api/mid-section-defect/analysis/detail` SHALL read from spool via DuckDB using a stable canonical identifier for the corresponding MSD query.

#### Scenario: Detail with explicit `trace_query_id`
- **WHEN** detail is requested with a valid `trace_query_id`
- **THEN** the endpoint SHALL resolve the matching spool and paginate/sort via DuckDB

#### Scenario: Compatibility request without explicit `trace_query_id`
- **WHEN** detail is requested using only legacy date/station/direction parameters during the migration window
- **THEN** the service SHALL resolve those parameters to the matching canonical MSD query before reading spool
- **THEN** it SHALL NOT guess based on a transient cache correlation key alone

#### Scenario: Detail spool miss
- **WHEN** detail is requested for an MSD query whose canonical spool is missing or unreadable
- **THEN** the endpoint SHALL return HTTP 410 with `{ success: false, error: "cache_expired" }`
- **THEN** the endpoint SHALL NOT enqueue a replacement MSD analysis job from the detail route

### Requirement: MSD export endpoint SHALL stream from the canonical spool
`GET /api/mid-section-defect/export` SHALL stream CSV data from the canonical MSD spool via DuckDB.

#### Scenario: Export with matching spool
- **WHEN** export is requested for a completed MSD query
- **THEN** the endpoint SHALL locate the corresponding canonical spool
- **THEN** it SHALL stream CSV rows without rerunning the full Oracle pipeline

#### Scenario: Export spool miss
- **WHEN** export is requested for an MSD query whose canonical spool is missing or unreadable
- **THEN** the endpoint SHALL return HTTP 410 with `{ success: false, error: "cache_expired" }`
- **THEN** the endpoint SHALL NOT enqueue a replacement MSD analysis job from the export route
