# query-tool-safety-hardening Specification

## Purpose
TBD - created by archiving change unified-lineage-engine. Update Purpose after archive.
## Requirements
### Requirement: query-tool resolve functions SHALL use QueryBuilder bind params for all user input
All `resolve_lots()` family functions (`_resolve_by_lot_id`, `_resolve_by_serial_number`, `_resolve_by_work_order`) SHALL use `QueryBuilder.add_in_condition()` with bind parameters instead of `_build_in_filter()` string concatenation.

#### Scenario: Lot resolve with user-supplied values
- **WHEN** a resolve function receives user-supplied lot IDs, serial numbers, or work order names
- **THEN** the SQL query SHALL use `:p0, :p1, ...` bind parameters via `QueryBuilder`
- **THEN** `read_sql_df()` SHALL receive `builder.params` (never an empty `{}` dict for queries with user input)
- **THEN** `_build_in_filter()` and `_build_in_clause()` SHALL NOT be called

#### Scenario: Pure static SQL without user input
- **WHEN** a query contains no user-supplied values (e.g., static lookups)
- **THEN** empty params `{}` is acceptable
- **THEN** no `_build_in_filter()` SHALL be used

#### Scenario: Zero residual references to deprecated functions
- **WHEN** the refactoring is complete
- **THEN** grep for `_build_in_filter` and `_build_in_clause` SHALL return zero results across the entire codebase

### Requirement: query-tool routes SHALL apply rate limiting
All query-tool API endpoints SHALL apply per-client rate limiting using the existing `configured_rate_limit` mechanism.

#### Scenario: Resolve endpoint rate limit exceeded
- **WHEN** a client sends more than 10 requests to query-tool resolve endpoints within 60 seconds
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header
- **THEN** the resolve service function SHALL NOT be called

#### Scenario: History endpoint rate limit exceeded
- **WHEN** a client sends more than 20 requests to query-tool history endpoints within 60 seconds
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header

#### Scenario: Association endpoint rate limit exceeded
- **WHEN** a client sends more than 20 requests to query-tool association endpoints within 60 seconds
- **THEN** the endpoint SHALL return HTTP 429 with a `Retry-After` header

### Requirement: query-tool routes SHALL apply response caching
High-cost query-tool endpoints SHALL cache responses in L2 Redis.

#### Scenario: Resolve result caching
- **WHEN** a resolve request succeeds
- **THEN** the response SHALL be cached in L2 Redis with TTL = 60s
- **THEN** subsequent identical requests within TTL SHALL return cached result without Oracle query

### Requirement: lot_split_merge_history SHALL support fast and full query modes
The `lot_split_merge_history.sql` query SHALL support two modes to balance traceability completeness vs performance.

#### Scenario: Fast mode (default)
- **WHEN** `full_history` query parameter is absent or `false`
- **THEN** the SQL SHALL include `TXNDATE >= ADD_MONTHS(SYSDATE, -6)` time window and `FETCH FIRST 500 ROWS ONLY`
- **THEN** query response time SHALL be ≤5s (P95)

#### Scenario: Full mode
- **WHEN** `full_history=true` query parameter is provided
- **THEN** the SQL SHALL NOT include time window restriction
- **THEN** the query SHALL use `read_sql_df_slow` (120s timeout)
- **THEN** query response time SHALL be ≤60s (P95)

