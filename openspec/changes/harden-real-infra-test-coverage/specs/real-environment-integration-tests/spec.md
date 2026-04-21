## ADDED Requirements

### Requirement: Real Oracle fault injection tier SHALL exist under `tests/integration/`

A dedicated test file `tests/integration/test_real_oracle_fault_injection.py` SHALL exercise the real `oracledb` driver against a real Oracle database container with network-level fault injection via a toxiproxy sidecar. Tests SHALL verify behaviour that cannot be asserted by mock-layer tests (`tests/integration/test_oracle_error_codes.py`): real driver exception types under session kill, listener stop, snapshot too old, and network flap; pool checkout/checkin accounting after failure; real socket-level reconnect within `socket_timeout`; circuit breaker counter increments from real driver failures. All tests in this file SHALL be marked `@pytest.mark.integration_real`.

#### Scenario: Session kill returns connection to pool

- **WHEN** a query is in flight and the Oracle session is terminated via `ALTER SYSTEM KILL SESSION`
- **THEN** the driver SHALL raise `oracledb.OperationalError` (or subclass) carrying ORA-00028
- **THEN** the pool's `busy` count SHALL return to zero after `conn.close()`
- **THEN** a subsequent query on a new pool connection SHALL succeed

*(HTTP envelope assertion — which `core/response.py` error code the route returns — is Phase 2B; requires the app-bridge prerequisite.)*

#### Scenario: Listener stop raises driver error  *(Phase 2A: driver-level only)*

- **WHEN** the toxiproxy `timeout` toxic is applied to the Oracle-proxy route
- **THEN** the driver SHALL raise `oracledb.OperationalError` or `oracledb.DatabaseError`
- **THEN** the exception message SHALL contain an `ORA-` error code

*(Route response code and `Retry-After` header assertions are Phase 2B. `DB_TRANSIENT_ERROR` is not a defined error code in `core/response.py` and SHALL NOT appear in Phase 2A tests.)*

#### Scenario: Listener recovery reconnects within socket timeout

- **WHEN** the toxic is cleared and a subsequent query is issued
- **THEN** the next request SHALL reconnect and complete within the configured `socket_timeout`
- **THEN** no manual worker restart SHALL be required

#### Scenario: Snapshot too old surfaces retryable envelope

- **WHEN** a long-running query runs against a segment where `UNDO_RETENTION` has been undercut
- **THEN** the driver SHALL raise `oracledb.DatabaseError` carrying ORA-01555
- **THEN** the route SHALL respond with the retryable envelope category, not 500 INTERNAL_ERROR

#### Scenario: Network flap mid-transaction rolls back cleanly

- **WHEN** a `reset_peer` toxic is applied mid-transaction for 5 seconds and then cleared
- **THEN** the un-committed transaction SHALL roll back (verified by querying absence of side-effect row)
- **THEN** the next request from the same pool SHALL succeed

#### Scenario: Latency spike does not leak pool connections

- **WHEN** a 600ms latency toxic is held for 60 seconds and the application issues ~120 requests during that window
- **THEN** after the toxic clears and queue drains, the pool's `checkout - checkin` balance SHALL equal zero
- **THEN** no `sqlalchemy.exc.TimeoutError` SHALL escape the service layer without being translated into the documented retryable envelope

#### Scenario: Circuit breaker counts real driver failures  *(Phase 2B — requires app bridge)*

- **WHEN** the toxiproxy `timeout` toxic is held and N consecutive requests fail against the real driver routed through `read_sql_df()`
- **THEN** each failure SHALL increment the circuit breaker failure counter via the `record_failure()` call at `core/database.py`
- **THEN** after the configured threshold the next request SHALL short-circuit with `error.code='CIRCUIT_BREAKER_OPEN'`

*Prerequisite: the Oracle XE DSN must be injectable into the Flask app factory's engine config (app bridge). Until that bridge exists, this scenario cannot be validated end-to-end with real driver failures.*

### Requirement: Conftest SHALL provide `oracle_xe` and `oracle_xe_fault` fixtures

`tests/integration/_oracle_xe_fixture.py` SHALL expose two fixtures usable by any test in the `integration_real` tier:
- `oracle_xe` (session-scoped): wait for the Oracle container to accept connections (max 240 seconds), create a dedicated `MES_TEST` schema and user, yield the DSN string, drop the schema on teardown.
- `oracle_xe_fault` (function-scoped): expose `add_toxic(name, type, attrs)` and `clear_toxics()` helpers that call the toxiproxy HTTP API via stdlib `urllib.request`; teardown SHALL clear all toxics registered during the test.

#### Scenario: `oracle_xe` yields a usable DSN

- **WHEN** a test requests the `oracle_xe` fixture
- **THEN** the fixture SHALL yield a DSN string
- **THEN** `oracledb.connect(dsn=...)` SHALL succeed
- **THEN** `SELECT 1 FROM DUAL` SHALL return `1`

#### Scenario: `oracle_xe_fault` adds and clears toxics

- **WHEN** a test calls `oracle_xe_fault.add_toxic('latency', 'latency', {'latency': 500})`
- **THEN** subsequent queries SHALL observe ≥ 500ms added latency
- **WHEN** the test returns and teardown runs
- **THEN** the proxy SHALL have zero toxics registered

#### Scenario: Readiness polling fails fast on environment error

- **WHEN** the Oracle container cannot be reached within 240 seconds
- **THEN** the fixture SHALL raise `pytest.fail("Oracle XE not ready after 240s; check CI service container logs")`
- **THEN** the test session SHALL fail rather than hang

### Requirement: Soak workload tier SHALL exist under `tests/integration/`

A dedicated test file `tests/integration/test_soak_workload.py` SHALL spawn real gunicorn workers, drive sustained low-pressure traffic against five high-traffic endpoints for a configurable duration, sample observability metrics at regular intervals, and assert that time-series properties indicate no progressive resource regression. Tests SHALL be marked `@pytest.mark.soak` (distinct from `integration_real` so they can be filtered independently).

#### Scenario: Soak suite spawns workers and drives sustained traffic

- **WHEN** the soak fixture starts with `duration_seconds=1800` and `sample_interval_seconds=30`
- **THEN** at least 2 gunicorn workers SHALL be spawned via the existing `gunicorn_workers` fixture
- **THEN** a background thread SHALL issue 2–5 requests/second across Query Tool, Reject History, Hold Overview, WIP Overview, and Resource History endpoints
- **THEN** another thread SHALL snapshot `/internal/metrics` every `sample_interval_seconds` and append to a time-series list

#### Scenario: Pool checkout/checkin delta does not grow monotonically

- **WHEN** the soak run completes
- **THEN** the linear regression slope of `pool.checkout - pool.checkin` over the time series SHALL have absolute value < 0.05 per sample
- **THEN** failure SHALL include the slope value and the time-series artifact path

#### Scenario: DuckDB temp files remain bounded

- **WHEN** the soak run completes
- **THEN** the maximum `duckdb.temp_bytes` observed SHALL NOT exceed 3× the first-quartile value
- **THEN** failure SHALL include min / Q1 / median / max / p95 of the time series

#### Scenario: Redis key count converges

- **WHEN** the soak run completes
- **THEN** the mean of the last 5 `redis.key_count` samples SHALL be within ±10% of the mean of the first 5 samples
- **THEN** failure SHALL report the starting mean, ending mean, and percent drift

#### Scenario: Worker RSS growth is bounded

- **WHEN** the soak run completes
- **THEN** the maximum `worker.rss_bytes` increase from baseline (first sample) across any worker SHALL be < 15%
- **THEN** failure SHALL identify the offending worker PID and growth percentage

#### Scenario: Circuit breaker transitions remain bounded

- **WHEN** the soak run completes
- **THEN** the total number of circuit breaker state transitions (closed→open, open→half-open, half-open→closed) SHALL be < 3
- **THEN** excessive transitions (≥ 3) SHALL fail the test and log every transition timestamp

#### Scenario: RQ queue depth does not grow unboundedly

- **WHEN** the soak run completes
- **THEN** for each RQ queue observed, the mean of the last 5 samples' pending depth SHALL be ≤ 1.5 × the mean of the first 5 samples' pending depth
- **THEN** failure SHALL name the offending queue and report starting mean, ending mean, and growth ratio
- **THEN** this assertion catches "no resource leak but backlog creeps upward" regressions that would be invisible without queue-depth observation

#### Scenario: Time-series artifact is always produced

- **WHEN** the soak run ends (pass OR fail)
- **THEN** a file `soak-metrics-<timestamp>.json` SHALL be written to the test artifact directory
- **THEN** the file SHALL contain the full time series with schema `{timestamp, pool, duckdb, redis, spool, worker_rss, circuit_breaker, rq}`

#### Scenario: Soak duration is explicitly bounded and documented as short-to-medium-term leak detection

- **WHEN** the soak test module is inspected
- **THEN** the module docstring SHALL state that the default 30-minute run detects short-to-medium-term leaks only
- **THEN** the docstring SHALL state that passing this test is NOT proof of absence of all leaks
- **THEN** the docstring SHALL state the 120-minute `workflow_dispatch` override as the upper bound for automated CI investigation
- **THEN** slower regressions (8h+ drift) SHALL be documented as out of scope for this test

### Requirement: `/internal/metrics` endpoint SHALL be gated by three independent layers and SHALL NOT be part of any production deploy config

The Flask application SHALL expose `GET /internal/metrics` only through the conjunction of three independent gates:

1. **Layer 1 (registration-time gate)** — The `internal_routes` blueprint SHALL only be imported and registered when the app config contains `register_internal_metrics=True`. Only the testing / nightly / soak config factories SHALL set this flag. Production config factories SHALL NOT import the `internal_routes` module at all; the URL map SHALL NOT contain any rule for `/internal/metrics` in production.
2. **Layer 2 (runtime env gate)** — Even when the blueprint is registered, the route handler SHALL first check `os.getenv("INTERNAL_METRICS_ENABLED") == "1"` and return `not_found_error()` (404) otherwise.
3. **Layer 3 (network defense-in-depth)** — The handler SHALL additionally check `request.remote_addr in {"127.0.0.1", "::1"}` and return `not_found_error()` otherwise. This layer is defense-in-depth only; the security posture SHALL NOT rely on `remote_addr` alone.

The response SHALL use the existing `success_response()` helper from `core/response.py` and return a JSON dict with **seven** keys: `pool`, `duckdb`, `redis`, `spool`, `worker_rss`, `circuit_breaker`, `rq`.

The endpoint SHALL be explicitly documented as an internal-only app surface (not an admin API precursor, not a stepping stone to future observability endpoints).

#### Scenario: Production config does not register the blueprint

- **WHEN** the production Flask app factory runs
- **THEN** the `internal_routes` module SHALL NOT be imported (verified via `sys.modules`)
- **THEN** the Flask URL map SHALL NOT contain any rule matching `/internal/metrics`
- **THEN** any HTTP request to `/internal/metrics` SHALL return Flask's default 404

#### Scenario: Testing config registers but runtime env gate blocks

- **WHEN** `config.register_internal_metrics=True` AND `INTERNAL_METRICS_ENABLED` is unset or set to a value other than `"1"`
- **WHEN** a loopback client requests `GET /internal/metrics`
- **THEN** the response SHALL be a 404 envelope from `not_found_error()`

#### Scenario: All gates open for loopback callers

- **WHEN** `config.register_internal_metrics=True` AND `INTERNAL_METRICS_ENABLED=1` AND the request comes from `remote_addr='127.0.0.1'`
- **THEN** the response SHALL be `success_response(...)` with status 200
- **THEN** `response.json['data']` SHALL contain all seven keys: `pool`, `duckdb`, `redis`, `spool`, `worker_rss`, `circuit_breaker`, `rq`
- **THEN** the `rq` key SHALL itself be a dict mapping each queue name to `{pending, started, failed, finished, deferred}` integer depths
- **THEN** each top-level metric SHALL be a JSON-serializable primitive or object

#### Scenario: Non-loopback request is rejected even when other gates are open

- **WHEN** `config.register_internal_metrics=True` AND `INTERNAL_METRICS_ENABLED=1` AND a request arrives with `remote_addr='10.0.0.5'`
- **THEN** the response SHALL be a 404 envelope from `not_found_error()`
- **THEN** the response body SHALL NOT contain any internal metrics data
- **THEN** the access log SHALL record the rejected remote_addr

#### Scenario: Endpoint is listed in API inventory as Internal-only

- **WHEN** `contract/api_inventory.md` is inspected
- **THEN** `/internal/metrics` SHALL appear under an explicit `Internal-only` classification (distinct from any user-facing or admin classification)
- **THEN** the entry SHALL note all three gate layers
- **THEN** the entry SHALL explicitly state that this endpoint is NOT an admin API precursor and is NOT included in any production deploy config

### Requirement: Real Oracle fault injection SHALL run in dedicated nightly CI job

A new GitHub Actions job `oracle-fault-injection` SHALL run the Oracle fault injection test suite on the `schedule` and `workflow_dispatch` events only (not on `pull_request`). The job SHALL declare `gvenzl/oracle-xe:21-slim` and `shopify/toxiproxy:2.9` as `services:`, wait for both to be ready, and execute `pytest tests/integration/test_real_oracle_fault_injection.py --run-integration-real`. The job SHALL NOT be required for pre-merge.

#### Scenario: Pre-merge CI does not trigger the Oracle fault injection job

- **WHEN** a pull request is opened
- **THEN** the `oracle-fault-injection` job SHALL NOT be scheduled
- **THEN** pre-merge total runtime SHALL NOT include the Oracle fault injection suite

#### Scenario: Nightly CI triggers the Oracle fault injection job

- **WHEN** the nightly schedule fires
- **THEN** the `oracle-fault-injection` job SHALL execute
- **THEN** any test failure SHALL mark the nightly build as failed

### Requirement: Soak workload SHALL run in weekly CI job

A new GitHub Actions workflow `soak-tests.yml` SHALL trigger on a weekly `cron` schedule (e.g., Sundays at 04:00 UTC) and on `workflow_dispatch`. The job SHALL have `timeout-minutes: 60`, run the soak suite with default `duration_seconds=1800`, and upload the `soak-metrics-*.json` artifact with a 30-day retention.

#### Scenario: Weekly soak job uploads metrics artifact

- **WHEN** the weekly soak job runs to completion
- **THEN** the `soak-metrics-*.json` file SHALL be uploaded as a GitHub Actions artifact
- **THEN** the artifact SHALL be retained for 30 days
- **THEN** any assertion failure SHALL fail the job AND still upload the artifact

#### Scenario: `workflow_dispatch` supports custom duration override

- **WHEN** the soak job is manually dispatched with input `duration_seconds=7200`
- **THEN** the soak suite SHALL run for 2 hours
- **THEN** job `timeout-minutes` SHALL be configured high enough to accommodate override (≥ 150 minutes)
