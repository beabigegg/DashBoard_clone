## ADDED Requirements

### Requirement: Oracle `cx_Oracle.DatabaseError` with specific ORA-* codes SHALL be covered by integration tests

A new integration test file `tests/integration/test_oracle_error_codes.py` SHALL verify that the database error handler translates representative `cx_Oracle.DatabaseError` instances (carrying ORA-* codes) into the correct API envelope and circuit-breaker counter increments. Testing SHALL cover at minimum: `ORA-01017` (invalid username/password), `ORA-12514` (listener refused connection), `ORA-01555` (snapshot too old).

#### Scenario: ORA-01017 surfaces auth failure envelope

- **WHEN** the engine's `execute` is patched to raise `cx_Oracle.DatabaseError('ORA-01017: invalid username/password')` during a route call
- **THEN** the response envelope SHALL carry `error.code='DB_AUTH_ERROR'` or an equivalent predefined code from `core/response.py`
- **THEN** the HTTP status SHALL be 503 or 500 as defined by the contract, never leak the raw ORA message in `error.message` untrimmed

#### Scenario: ORA-12514 counts toward circuit breaker

- **WHEN** the engine raises `cx_Oracle.DatabaseError('ORA-12514: listener refused')` repeatedly
- **THEN** each failure SHALL increment the circuit breaker failure counter
- **THEN** after the configured threshold the next request SHALL short-circuit with `error.code='CIRCUIT_BREAKER_OPEN'`

#### Scenario: ORA-01555 is classified as transient retryable

- **WHEN** the engine raises `cx_Oracle.DatabaseError('ORA-01555: snapshot too old')`
- **THEN** the response envelope SHALL use the retryable category (`DB_TRANSIENT_ERROR` or equivalent)
- **THEN** the envelope SHALL include `Retry-After` header and `meta.retry_after_seconds`

### Requirement: Redis socket-level timeout and reconnect SHALL be covered by integration tests

A new integration test file `tests/integration/test_redis_timeout_fallback.py` SHALL use the existing `local_redis` fixture to start a real redis-server, induce socket-level timeouts via `DEBUG SLEEP`, and verify that filter caches and in-process caches fall back to `_ProcessLevelCache` without leaking tracebacks to the API layer.

#### Scenario: Filter cache falls back to in-memory on Redis timeout

- **WHEN** `redis.Redis` is configured with `socket_timeout=0.1` and `DEBUG SLEEP 1` is issued before a filter-cache read
- **THEN** the cache API SHALL raise or swallow `redis.exceptions.TimeoutError` and fall back to the in-memory `_ProcessLevelCache`
- **THEN** the downstream route SHALL respond with `success: true` and valid cached / computed data
- **THEN** no 500 response SHALL leak to the client

#### Scenario: Reconnect succeeds after Redis returns to normal

- **WHEN** the timeout is cleared (DEBUG SLEEP finishes) and a subsequent filter-cache read is issued
- **THEN** the next request SHALL observe the Redis client reconnect and complete within `socket_timeout`
- **THEN** the cache-hit metric SHALL resume incrementing

### Requirement: Cache and spool race conditions SHALL be covered by integration tests

A new integration test file `tests/integration/test_race_conditions.py` SHALL use `threading.Thread` + `threading.Barrier` to trigger deterministic race conditions on: (a) two concurrent writes to the same cache key, (b) two concurrent export spool file creations for the same report+user+range, (c) concurrent read during spool cleanup.

#### Scenario: Concurrent cache writes produce deterministic final value

- **WHEN** two threads synchronized by `Barrier(2)` both call `cache.set(key='X', value=...)` with different values
- **THEN** the final stored value SHALL be one of the two inputs (not a merged/corrupted value)
- **THEN** no exception SHALL escape the service layer

#### Scenario: Concurrent spool file creation deduplicates via lock

- **WHEN** two threads with the same `(user_id, report_type, params_hash)` simultaneously trigger export
- **THEN** only one spool file SHALL be written
- **THEN** both callers SHALL receive the same `query_id` referencing that file

#### Scenario: Spool read during cleanup never observes corrupted parquet

- **WHEN** a reader opens a spool parquet file and the cleanup thread attempts to delete the same file within 100ms of the open call
- **THEN** the reader SHALL either complete successfully or receive `error.code='CACHE_EXPIRED'`
- **THEN** no `ParquetInvalidError` or truncated-file error SHALL propagate to the client

### Requirement: Route tests SHALL include malformed-input fuzz parametrization

A shared fixture file `tests/routes/_fuzz_payloads.py` SHALL expose `MALICIOUS_INPUTS` — a list of at least 6 canonical malicious / edge payloads (SQL-special characters, oversized string, Unicode/emoji, whitespace-only, inverted date range, negative pagination). Every route test file that exercises a query-accepting endpoint SHALL include a `@pytest.mark.parametrize` case sweeping these payloads and assert that the response carries a 400-class status with `error.code='VALIDATION_ERROR'`, never a 500 or raw traceback.

#### Scenario: SQL-special payload returns VALIDATION_ERROR

- **WHEN** a route is called with `lot_id="LOT-001'; DROP TABLE--"` via the Flask test client
- **THEN** the response status SHALL be 400 or 422
- **THEN** `response.json['error']['code']` SHALL equal `VALIDATION_ERROR` (or a predefined sub-code)
- **THEN** the Flask test client SHALL NOT observe a 500-class response

#### Scenario: Oversized string input is rejected

- **WHEN** a route receives an input field with a 100,000-character string
- **THEN** the response SHALL carry a 400-class status with `VALIDATION_ERROR`
- **THEN** no Oracle query SHALL be dispatched (verified by patching engine and asserting zero calls)

#### Scenario: Unicode / emoji payload does not cause encoding errors

- **WHEN** a route receives `filter="🚀-測試-ñoño"` and the schema expects ASCII-only
- **THEN** the response SHALL carry `VALIDATION_ERROR`
- **THEN** the response body SHALL still be valid UTF-8 JSON

#### Scenario: Inverted date range rejected at route layer

- **WHEN** a route receives `start_date=2026-03-15&end_date=2026-03-01`
- **THEN** the response SHALL carry `VALIDATION_ERROR` with a message referring to the inverted range
- **THEN** no `_query_execution` call SHALL be made (verified by mock spy)

#### Scenario: Negative pagination values are rejected

- **WHEN** a route receives `page=-1&per_page=-50` or `per_page=99999`
- **THEN** the response SHALL carry `VALIDATION_ERROR`
- **THEN** defaults SHALL NOT silently replace the negative values

### Requirement: Oracle ORA-code tests, Redis timeout tests, and race-condition tests SHALL run in nightly CI

The three new integration test files SHALL be marked with `@pytest.mark.integration_real` and SHALL be executed by the nightly CI workflow via `pytest --run-integration-real tests/integration/test_oracle_error_codes.py tests/integration/test_redis_timeout_fallback.py tests/integration/test_race_conditions.py`. Pre-merge CI SHALL NOT execute these tests by default.

#### Scenario: Pre-merge CI skips integration_real tests

- **WHEN** pre-merge CI runs `pytest` without the `--run-integration-real` flag
- **THEN** the three new files SHALL be skipped
- **THEN** the session SHALL succeed

#### Scenario: Nightly CI runs and gates on integration_real tests

- **WHEN** the nightly workflow runs `pytest --run-integration-real tests/integration/`
- **THEN** all three new files SHALL execute
- **THEN** any failure SHALL mark the nightly build as failed

### Requirement: Backend resilience tests SHALL document reverse-verification before merge

Each new integration test file under this change SHALL have a reverse-verification note in the PR description: temporarily removing the corresponding error handler (for ORA-code mapping) or fallback logic (for Redis) SHALL cause the new test to FAIL. Tests that still pass after the handler is removed SHALL be rejected in review.

#### Scenario: PR description lists mutation-check outcome

- **WHEN** a PR adds `test_oracle_error_codes.py`
- **THEN** the description SHALL identify which handler in `core/response.py` or `services/*.py` was temporarily removed to prove the test catches the regression
- **THEN** the reviewer SHALL verify the proof before approving
