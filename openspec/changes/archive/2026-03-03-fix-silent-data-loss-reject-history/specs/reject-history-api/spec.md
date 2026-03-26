## MODIFIED Requirements

### Requirement: Reject History API SHALL validate required query parameters
The API SHALL validate date parameters and basic paging bounds before executing database work.

#### Scenario: Missing required dates
- **WHEN** a reject-history endpoint requiring date range is called without `start_date` or `end_date`
- **THEN** the API SHALL return HTTP 400 with a descriptive validation error

#### Scenario: Invalid date order
- **WHEN** `end_date` is earlier than `start_date`
- **THEN** the API SHALL return HTTP 400 and SHALL NOT run SQL queries

#### Scenario: Date range exceeds maximum
- **WHEN** the date range between `start_date` and `end_date` exceeds 730 days
- **THEN** the API SHALL return HTTP 400 with error message "日期範圍不可超過 730 天"

## ADDED Requirements

### Requirement: Reject History API primary query response SHALL include partial failure metadata
The primary query endpoint SHALL include batch execution completeness information in the response `meta` field when chunks fail during batch query execution.

#### Scenario: Partial failure metadata in response
- **WHEN** `POST /api/reject-history/query` completes with some chunks failing
- **THEN** the response SHALL include `meta.has_partial_failure: true`
- **THEN** the response SHALL include `meta.failed_chunk_count` as a positive integer
- **THEN** the response SHALL include `meta.failed_ranges` as an array of `{start, end}` date strings (if available)
- **THEN** the HTTP status SHALL still be 200 (data is partially available)

#### Scenario: No partial failure metadata on full success
- **WHEN** `POST /api/reject-history/query` completes with all chunks succeeding
- **THEN** the response `meta` SHALL NOT include `has_partial_failure`, `failed_chunk_count`, or `failed_ranges`

#### Scenario: Partial failure metadata preserved on cache hit
- **WHEN** `POST /api/reject-history/query` returns cached data that originally had partial failures
- **THEN** the response SHALL include the same `meta.has_partial_failure`, `meta.failed_chunk_count`, and `meta.failed_ranges` as the original response
