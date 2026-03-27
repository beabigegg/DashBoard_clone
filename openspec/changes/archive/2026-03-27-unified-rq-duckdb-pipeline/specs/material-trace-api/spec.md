## MODIFIED Requirements

### Requirement: Material trace SHALL migrate to spool-backed execution
Material trace queries and export SHALL migrate to RQ + parquet spool + DuckDB runtime so that large result sets no longer depend on in-memory full-result processing.

#### Scenario: Spool hit
- **WHEN** a material trace request matches a valid spool
- **THEN** the route SHALL return paginated/query results from DuckDB over the existing spool

#### Scenario: Spool miss on async-capable path
- **WHEN** no spool exists and the async contract has been enabled for material trace
- **THEN** the route SHALL enqueue the request and return HTTP 202

### Requirement: Material trace row-limit retirement SHALL follow async/runtime migration
The existing `_REVERSE_MAX_ROWS`, `_FORWARD_MAX_ROWS`, and `_EXPORT_MAX_ROWS` limits SHALL only be removed after spool-backed runtime and frontend async handling are in place.

#### Scenario: Legacy path still active
- **WHEN** the legacy sync/materialization path is still in service
- **THEN** current safety limits SHALL remain

#### Scenario: Migration complete
- **WHEN** spool-backed query, pagination, export, and frontend polling support are complete
- **THEN** the legacy row limits MAY be removed
