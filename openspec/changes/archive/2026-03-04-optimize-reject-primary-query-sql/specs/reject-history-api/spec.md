## ADDED Requirements

### Requirement: Reject History API SHALL preserve paginated list contract after primary-query decoupling
The API SHALL keep `GET /api/reject-history/list` behavior and response schema stable after `/query` switches to a dedicated SQL source.

#### Scenario: List endpoint pagination schema remains stable
- **WHEN** `GET /api/reject-history/list` is called with valid date range and paging params
- **THEN** the response SHALL still include `items` and `pagination` with `page`, `perPage`, `total`, and `totalPages`
- **THEN** the endpoint SHALL continue to support page-bound retrieval semantics

#### Scenario: List endpoint sorting semantics remain stable
- **WHEN** two equivalent list requests are executed before and after the primary-query decoupling change
- **THEN** row ordering semantics SHALL remain consistent with existing list contract

### Requirement: Reject History API primary response contract SHALL remain backward compatible
Switching the primary SQL source SHALL NOT alter `/api/reject-history/query` response fields consumed by the current UI flow.

#### Scenario: Primary query response shape is unchanged
- **WHEN** `POST /api/reject-history/query` succeeds
- **THEN** the response SHALL continue to include `query_id`, `summary`, `trend`, `detail`, `available_filters`, and `meta`
- **THEN** existing `/view` and `/export-cached` workflows SHALL remain compatible with the returned `query_id`

#### Scenario: Cache-hit behavior remains unchanged
- **WHEN** the same primary query is executed again within cache lifetime
- **THEN** cache-hit behavior SHALL remain functionally equivalent to pre-decoupling behavior
- **THEN** response field names and types SHALL remain stable
