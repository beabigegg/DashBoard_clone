## ADDED Requirements

### Requirement: Oracle driver errors SHALL map to stable API response contracts
Raw Oracle driver exceptions reaching the Flask application boundary SHALL be
translated into stable API envelopes based on their ORA code rather than falling
through to the generic internal-error handler.

#### Scenario: ORA-01017 maps to database connection failure
- **WHEN** a request path raises an Oracle driver error with code `ORA-01017`
- **THEN** the API SHALL return a database-connection failure contract instead
  of generic `INTERNAL_ERROR`
- **THEN** the response SHALL NOT leak the raw driver message untrimmed

#### Scenario: Listener and connection-loss errors return retry-aware degraded response
- **WHEN** a request path raises `ORA-12514`, `ORA-12541`, `ORA-03113`, or
  `ORA-03135`
- **THEN** the API SHALL return HTTP 503 with a machine-readable database
  connection failure code
- **THEN** the response SHALL include `Retry-After`

#### Scenario: ORA-01555 maps to query-timeout contract
- **WHEN** a request path raises `ORA-01555`
- **THEN** the API SHALL return the query-timeout/retryable contract instead of
  generic `INTERNAL_ERROR`

#### Scenario: Unknown ORA code remains distinguishable from generic app failure
- **WHEN** a request path raises an unmapped ORA-coded driver error
- **THEN** the API SHALL return a stable database-originated failure contract
- **THEN** the response SHALL remain distinguishable from non-database generic
  application failures

