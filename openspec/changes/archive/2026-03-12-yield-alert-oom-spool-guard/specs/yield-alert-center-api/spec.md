## MODIFIED Requirements

### Requirement: Yield Alert Center API SHALL enforce query safety boundaries
The API SHALL prevent unbounded high-cardinality Oracle scans through explicit window limits, bounded response size, and interactive memory guards.

#### Scenario: Exceeding time window policy
- **WHEN** client requests a date range larger than configured maximum window
- **THEN** API SHALL reject the request with a validation error
- **THEN** response SHALL include a machine-readable reason indicating time-window violation

#### Scenario: Page size guardrail
- **WHEN** client requests `per_page` above configured maximum
- **THEN** API SHALL cap or reject according to policy
- **THEN** response SHALL expose effective page size in pagination metadata

#### Scenario: Memory guard rejection on primary query
- **WHEN** `execute_primary_query` returns a DataFrame exceeding `YIELD_ALERT_VIEW_MAX_INPUT_MB` or projected RSS exceeds `YIELD_ALERT_VIEW_MAX_PROJECTED_RSS_MB`
- **THEN** API SHALL return HTTP 503 with `SERVICE_UNAVAILABLE` error code
- **THEN** response SHALL include a human-readable message explaining the memory constraint
- **THEN** response SHALL include `Retry-After: 30` header

#### Scenario: Memory guard rejection on view query
- **WHEN** `apply_view` pandas fallback path detects DataFrame or projected RSS exceeding configured limits
- **THEN** API SHALL return HTTP 503 with `SERVICE_UNAVAILABLE` error code
- **THEN** response SHALL include a human-readable message explaining the memory constraint

### Requirement: Yield Alert Center API SHALL support performance-aware result reuse
The API SHALL support cache-aware execution for repeated equivalent queries, with parquet spool as the primary storage tier for view computations.

#### Scenario: Cache hit response
- **WHEN** the same normalized query parameters are requested within freshness window
- **THEN** API SHALL return cached aggregate/alert results
- **THEN** response metadata SHALL indicate cache hit status

#### Scenario: Cache miss response
- **WHEN** no reusable cache entry exists
- **THEN** API SHALL execute Oracle query path and return computed results
- **THEN** response metadata SHALL indicate cache miss status

#### Scenario: Parquet spool enables out-of-core view computation
- **WHEN** a parquet spool file exists for the query_id
- **THEN** `apply_view` SHALL compute results via DuckDB without loading the full DataFrame into process memory
- **THEN** peak RSS during view computation SHALL be bounded by DuckDB's memory-mapped execution model
