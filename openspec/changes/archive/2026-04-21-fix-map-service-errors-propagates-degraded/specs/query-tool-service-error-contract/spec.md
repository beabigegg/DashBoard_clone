## ADDED Requirements

### Requirement: Query-tool degraded database exceptions SHALL propagate to app-level handlers
Query-tool routes using `@map_service_errors` SHALL allow
`DatabaseDegradedError` subclasses to propagate so the Flask app-level degraded
handlers can emit retry-aware responses.

#### Scenario: Pool exhausted on query-tool route returns degraded response
- **WHEN** a query-tool service call raises `DatabasePoolExhaustedError`
- **THEN** the route SHALL respond with HTTP 503
- **THEN** the response SHALL expose `error.code = DB_POOL_EXHAUSTED`
- **THEN** the response SHALL include `Retry-After`

#### Scenario: Circuit open on query-tool route returns degraded response
- **WHEN** a query-tool service call raises `DatabaseCircuitOpenError`
- **THEN** the route SHALL respond with HTTP 503
- **THEN** the response SHALL expose `error.code = CIRCUIT_BREAKER_OPEN`
- **THEN** the response SHALL include `Retry-After`

#### Scenario: Unexpected non-degraded exception still returns internal error
- **WHEN** a query-tool route raises an unexpected exception that is not a known
  typed service error and not a `DatabaseDegradedError`
- **THEN** the decorator SHALL continue to log the error with traceback
- **THEN** the route SHALL return the standard internal-error response

