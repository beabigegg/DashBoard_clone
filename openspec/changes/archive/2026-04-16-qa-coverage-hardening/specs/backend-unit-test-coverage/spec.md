## ADDED Requirements

### Requirement: Previously untested routes and services SHALL have dedicated unit tests
The following modules SHALL each have a dedicated test file covering happy path, error envelope, and the primary edge cases listed in the proposal.

#### Scenario: analytics_routes unit tests exist
- **WHEN** the test suite runs `tests/test_analytics_routes.py`
- **THEN** the suite SHALL cover `anomaly-summary` cache hit, cache miss with `meta.cache_state='cold'` disambiguation, and envelope `meta.generated_at` presence

#### Scenario: trace_lineage_job_service unit tests exist
- **WHEN** the test suite runs `tests/test_trace_lineage_job_service.py`
- **THEN** the suite SHALL cover canonical query_id stability across reordered filters, NDJSON stream line well-formedness, and job expiry non-raise behaviour

#### Scenario: msd_duckdb_runtime unit tests exist
- **WHEN** the test suite runs `tests/test_msd_duckdb_runtime.py`
- **THEN** the suite SHALL assert row count, key column presence, and null-column handling using `tests/fixtures/spool_snapshots/`

#### Scenario: query_tool_sql_runtime unit tests exist
- **WHEN** the test suite runs `tests/test_query_tool_sql_runtime.py`
- **THEN** the suite SHALL cover parameter binding, date-range guard, injection blocklist, and empty-result envelope

#### Scenario: user_auth_routes isolated unit tests exist
- **WHEN** the test suite runs `tests/test_user_auth_routes.py`
- **THEN** the suite SHALL cover login success, failure, locked account, remember_me, session expiry 401 envelope, and LDAP fault returning `DB_CONNECTION_FAILED` envelope (not HTTP 500)

#### Scenario: generic filter_cache unit tests exist
- **WHEN** the test suite runs `tests/test_filter_cache_generic.py`
- **THEN** the suite SHALL cover TTL expiry, stampede protection, and Redis-disabled fallback

### Requirement: OEE and numeric precision SHALL be pinned by unit tests
Numeric calculations and type normalisation SHALL be verified so that Decimal/float/str drift from Oracle is caught at the unit layer.

#### Scenario: OEE four-decimal stability
- **WHEN** `tests/test_oee_precision.py` runs against the canonical fixture set
- **THEN** all OEE values SHALL equal `round(x, 4)` and remain stable across runs

#### Scenario: Decimal normalised to float
- **WHEN** SQL runtime tests observe a numeric column
- **THEN** the service layer output SHALL be `float`, not `Decimal` or `str`

#### Scenario: Timestamps normalised to ISO-8601 UTC string
- **WHEN** a route returns a timestamp field
- **THEN** the field SHALL be an ISO-8601 UTC string with explicit offset (no naive datetime)

### Requirement: Envelope runtime sweep SHALL validate all registered routes
`tests/test_api_contract.py` SHALL be extended with a `TestEnvelopeRuntimeSweep` class that exercises every registered route via `app.test_client()` and asserts envelope compliance.

#### Scenario: All routes covered by runtime sweep
- **WHEN** the runtime sweep executes
- **THEN** at least 90% of non-exempted routes SHALL be hit with the sample params provided by `tests/fixtures/route_contract_matrix.py`
- **THEN** each response SHALL satisfy either the success-envelope or error-envelope shape

#### Scenario: Missing matrix entry fails test
- **WHEN** a new route is added without a corresponding entry in `route_contract_matrix.py`
- **THEN** `test_route_matrix_complete` SHALL fail with a diagnostic listing the missing endpoint

#### Scenario: Error codes drawn from allowlist
- **WHEN** a fault-injected request produces an error envelope
- **THEN** `error.code` SHALL be a member of the allowlist imported from `src/mes_dashboard/core/response.py`

### Requirement: Datetime normalisation SHALL be anchored to Asia/Taipei
Date parsing for "today" / "this shift" semantics SHALL be anchored to `Asia/Taipei` regardless of client timezone.

#### Scenario: Today anchored to Taipei
- **WHEN** a request arrives at 23:30 UTC with `range='today'`
- **THEN** the service SHALL interpret "today" against the `Asia/Taipei` clock, not UTC
