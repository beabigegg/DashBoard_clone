## MODIFIED Requirements

### Requirement: MSD analysis compatibility endpoint SHALL remain available until consumer migration completes
`GET /api/mid-section-defect/analysis` SHALL remain available as a compatibility endpoint while MSD migrates to the staged trace + spool pipeline.

#### Scenario: Compatibility adapter
- **WHEN** `GET /api/mid-section-defect/analysis` is called during the migration window
- **THEN** the endpoint MAY internally execute the staged trace / spool / DuckDB pipeline
- **THEN** it SHALL preserve the existing response contract expected by current consumers

#### Scenario: Endpoint retirement
- **WHEN** the project proposes to remove `/api/mid-section-defect/analysis`
- **THEN** frontend consumers, AI function registry references, tests, and API inventory entries SHALL all be migrated first

### Requirement: MSD detail endpoint SHALL use a canonical spool identifier
`GET /api/mid-section-defect/analysis/detail` SHALL read from spool via DuckDB using a stable canonical identifier for the corresponding MSD query.

#### Scenario: Detail with explicit `trace_query_id`
- **WHEN** detail is requested with a valid `trace_query_id`
- **THEN** the endpoint SHALL resolve the matching spool and paginate/sort via DuckDB

#### Scenario: Compatibility request without explicit `trace_query_id`
- **WHEN** detail is requested using only legacy date/station/direction parameters during the migration window
- **THEN** the service SHALL resolve those parameters to the matching canonical MSD query before reading spool
- **THEN** it SHALL NOT guess based on a transient cache correlation key alone

### Requirement: MSD export endpoint SHALL stream from the canonical spool
`GET /api/mid-section-defect/export` SHALL stream CSV data from the canonical MSD spool via DuckDB.

#### Scenario: Export with matching spool
- **WHEN** export is requested for a completed MSD query
- **THEN** the endpoint SHALL locate the corresponding canonical spool
- **THEN** it SHALL stream CSV rows without rerunning the full Oracle pipeline
