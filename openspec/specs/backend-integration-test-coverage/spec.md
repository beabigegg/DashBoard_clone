## Purpose

Ensure every route module has integration tests covering success and error paths via the Flask test client.
## Requirements
### Requirement: Every route module SHALL have integration tests covering success and error paths
Each route module under `src/mes_dashboard/routes/` SHALL have a corresponding test file that exercises HTTP endpoints via the Flask test client, covering at least one success path and one error/validation path per endpoint.

#### Scenario: Route module with missing integration tests
- **WHEN** a route module exists at `routes/<name>.py` with no corresponding `tests/test_<name>_routes.py`
- **THEN** a new integration test file SHALL be created

#### Scenario: Identified gap routes
- **WHEN** auditing the following route modules: `dashboard_routes.py`, `spool_routes.py`, `user_auth_routes.py` (beyond basic auth tests)
- **THEN** each SHALL have integration tests for all registered endpoints

### Requirement: Integration tests SHALL verify response format compliance
All route integration tests SHALL assert that responses conform to the API contract — using `success_response` / error helpers from `core/response.py`.

#### Scenario: Successful API response
- **WHEN** a test calls an endpoint that returns success
- **THEN** the response JSON SHALL contain `"success": true` and a `"data"` field

#### Scenario: Validation error response
- **WHEN** a test calls an endpoint with invalid parameters
- **THEN** the response JSON SHALL contain `"success": false` and an `"error"` field with a predefined error code

### Requirement: Integration tests SHALL cover partial-failure responses
For endpoints that support partial-failure propagation, integration tests SHALL verify that partial failure metadata is correctly included in the response.

#### Scenario: Endpoint returns partial failure
- **WHEN** one of multiple data sources fails during a multi-source query
- **THEN** the response SHALL include partial failure indicators as defined by the API contract

### Requirement: Oracle pool and timeout boundaries SHALL be covered by integration tests
Fault-injected integration tests SHALL exercise the Oracle pool exhaustion and query timeout envelopes to guarantee that the circuit breaker and envelope error codes remain correct under stress.

#### Scenario: Pool exhaustion returns circuit breaker envelope
- **WHEN** `tests/test_oracle_pool_exhaustion.py` monkeypatches the engine pool to size 1 and issues N concurrent requests
- **THEN** overflow requests SHALL receive `{ error:{ code:'CIRCUIT_BREAKER_OPEN' }, meta:{ retry_after:... } }`

#### Scenario: Query timeout returns DB_QUERY_TIMEOUT envelope
- **WHEN** an Oracle query is forced to exceed 60 seconds
- **THEN** the envelope SHALL carry `error.code='DB_QUERY_TIMEOUT'` with HTTP 504

#### Scenario: Long query releases connection on timeout
- **WHEN** a long query times out
- **THEN** the Oracle connection SHALL be returned to the pool and the subsequent request SHALL succeed without exhaustion

### Requirement: Cache refill lifecycle SHALL be validated end-to-end
Cache miss → Oracle refill → Redis write → second-call hit SHALL be verified by a dedicated integration test.

#### Scenario: Miss-refill-hit cycle
- **WHEN** `tests/test_cache_lifecycle.py` exercises a cold cache key
- **THEN** the first request SHALL trigger one Oracle call, the second SHALL not
- **THEN** both requests SHALL return equivalent envelopes

#### Scenario: Stampede protection spans multiple workers
- **WHEN** 10 concurrent requests hit the same cold key across simulated workers
- **THEN** exactly one Oracle query SHALL be executed
- **THEN** all 10 requests SHALL return equivalent data

### Requirement: Spool lifecycle SHALL be validated across TTL, cleanup, and concurrency
Spool file lifecycle tests SHALL cover TTL boundaries, orphan cleanup, concurrent read/cleanup, and schema evolution.

#### Scenario: TTL expiry boundary
- **WHEN** a spool file's `expires_at` is in the past and cleanup runs
- **THEN** the file SHALL be removed AND subsequent read attempts SHALL receive `error.code='CACHE_EXPIRED'` with HTTP 410

#### Scenario: Orphan cleanup reclaims untracked parquet
- **WHEN** a parquet file exists in `QUERY_SPOOL_DIR` without a corresponding Redis entry beyond the grace period
- **THEN** the cleanup worker SHALL remove it

#### Scenario: Concurrent read during cleanup
- **WHEN** a reader loads a spool file while the cleanup thread runs
- **THEN** the reader SHALL either complete successfully or fail with `CACHE_EXPIRED` — never a corrupted parquet error

#### Scenario: Schema evolution back-fills null
- **WHEN** a spool file produced by an older schema lacks a newly added column
- **THEN** the reader SHALL populate the missing column with null rather than raising

### Requirement: Async job timeout and worker crash recovery SHALL be covered
`tests/test_async_job_timeout.py` and `tests/test_rq_worker_crash_recovery.py` SHALL validate timeout behaviour and crash reconciliation for async jobs.

#### Scenario: Oracle timeout marks job failed
- **WHEN** an async job's upstream Oracle query is forced to time out
- **THEN** the job status SHALL transition to `failed` with `error.code='DB_QUERY_TIMEOUT'`
- **THEN** the job SHALL NOT remain in `running` indefinitely

#### Scenario: SIGKILL mid-job reconciled on next sweep
- **WHEN** an RQ worker is SIGKILLed during a job
- **THEN** the next `StartedJobRegistry.cleanup()` sweep SHALL mark the job `failed`

#### Scenario: Restart does not rerun completed job
- **WHEN** an RQ worker restarts after completing a job
- **THEN** the job SHALL NOT be re-enqueued or re-executed

### Requirement: Oracle and DuckDB resource leaks SHALL be caught by integration tests
`tests/test_oracle_connection_leak.py` SHALL verify that running 100 async jobs leaves the Oracle pool at zero active connections. DuckDB file handle leaks SHALL be similarly verified.

#### Scenario: 100-job Oracle leak check
- **WHEN** 100 async jobs execute end-to-end
- **THEN** the Oracle pool active-connection count SHALL return to zero within 5 seconds

#### Scenario: DuckDB file handle cleanup
- **WHEN** 100 spool reads complete
- **THEN** no parquet or `.duckdb` file SHALL remain open per `lsof`

### Requirement: Rate limiting and distributed lock correctness SHALL be integration-tested
`tests/test_rate_limit.py` and `tests/test_distributed_lock.py` SHALL cover per-client rate limits and Redis lock primitives.

#### Scenario: Burst of duplicate requests triggers rate limit
- **WHEN** a single client issues more than the configured rate within 1 second
- **THEN** subsequent requests SHALL receive `error.code='TOO_MANY_REQUESTS'` without reaching Oracle

#### Scenario: Redis lock auto-expires on crash
- **WHEN** the lock holder crashes before releasing
- **THEN** the lock SHALL expire within its configured TTL and a subsequent contender SHALL acquire it

#### Scenario: Lock TTL covers p95 query time
- **WHEN** inspecting the configured lock TTL
- **THEN** it SHALL be at least the p95 query time plus a documented safety margin

### Requirement: Cross-worker result sharing SHALL be integration-tested
`tests/test_cross_worker_result_sharing.py` SHALL verify that async job state and spool results propagate across simulated gunicorn workers.

#### Scenario: Job visible from all workers
- **WHEN** a job is submitted via one simulated worker and polled via another
- **THEN** the polling worker SHALL observe the job state without `NOT_FOUND`

#### Scenario: Spool file readable from all workers
- **WHEN** a spool file is written by one worker and read by another
- **THEN** the reader SHALL observe identical rows with identical types

### Requirement: Heavy join queries SHALL respect query timeout and circuit breaker
`tests/test_query_tool_heavy_join.py` and `tests/test_circuit_breaker_integration.py` SHALL verify that complex join scenarios degrade gracefully.

#### Scenario: Multi-filter lineage join respects timeout
- **WHEN** a complex lineage query exceeds the query timeout
- **THEN** the envelope SHALL carry `error.code='DB_QUERY_TIMEOUT'` and SHALL NOT hang

#### Scenario: Repeated timeouts open the circuit breaker
- **WHEN** N consecutive heavy-query timeouts are observed
- **THEN** subsequent requests SHALL short-circuit with `error.code='CIRCUIT_BREAKER_OPEN'`

#### Scenario: Breaker half-opens after cooldown
- **WHEN** the circuit breaker cooldown elapses
- **THEN** a probe request SHALL be allowed through to test recovery

### Requirement: sync_worker deadlock retry regression SHALL be pinned
The deadlock retry fix from commit `a6fecb9` SHALL be protected by `tests/test_sync_worker_deadlock_retry.py`.

#### Scenario: executemany deadlock retried
- **WHEN** an executemany batch triggers a MySQL 1213 deadlock
- **THEN** the sync worker SHALL retry up to the configured limit and complete successfully

### Requirement: AI query service SHALL have edge-case envelope tests
`tests/test_ai_routes.py` SHALL be extended to cover context limits, tool traces, clarification loops, and conversation persistence.

#### Scenario: Context limit envelope
- **WHEN** a prompt exceeds the LLM context limit
- **THEN** the envelope SHALL carry `error.code='CONTEXT_LIMIT_REACHED'`

#### Scenario: Tool trace included when flag set
- **WHEN** `include_trace=true` is set on the request
- **THEN** `data.tool_trace` SHALL be present as an array of execution steps

#### Scenario: Clarification flow shape
- **WHEN** the LLM returns a clarification request
- **THEN** `data.needs_clarification === true` and `data.clarification_question` SHALL be present

#### Scenario: Conversation id round-trip through Redis
- **WHEN** a conversation is continued with an existing `conversation_id`
- **THEN** prior turns SHALL be retrievable from Redis regardless of which worker handles the follow-up

