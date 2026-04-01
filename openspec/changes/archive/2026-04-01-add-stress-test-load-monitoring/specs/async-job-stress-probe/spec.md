## ADDED Requirements

### Requirement: AsyncJobPoller helper SHALL encapsulate the 202 polling pattern
`tests/stress/async_helpers.py` SHALL provide an `AsyncJobPoller` class that handles the submit → poll → retrieve lifecycle for async heavy queries.

#### Scenario: Sync spool hit (HTTP 200)
- **WHEN** the API returns HTTP 200 (spool already exists)
- **THEN** `AsyncJobPoller` SHALL return the result immediately without entering the polling loop
- **THEN** `result.was_async` SHALL be `False`

#### Scenario: Async job submission (HTTP 202)
- **WHEN** the API returns HTTP 202 with `job_id` and `status_url`
- **THEN** `AsyncJobPoller` SHALL poll `status_url` at the configured interval until `status="completed"`
- **THEN** `result.was_async` SHALL be `True`, `result.poll_count` SHALL reflect the number of polls

#### Scenario: Job completed with dataset_id
- **WHEN** polling returns `status="completed"` with `dataset_id` or `query_id`
- **THEN** `AsyncJobPoller` SHALL re-query the original endpoint to retrieve the spool hit result
- **THEN** `result.data` SHALL contain the final query result

#### Scenario: Job failed
- **WHEN** polling returns `status="failed"` with an error message
- **THEN** `AsyncJobPoller` SHALL return `result.error` with the failure reason
- **THEN** no further polling SHALL occur

#### Scenario: Polling timeout
- **WHEN** the job does not complete within `max_wait` seconds (default 300s)
- **THEN** `AsyncJobPoller` SHALL raise `AsyncJobTimeout` with `job_id` and `elapsed` time

### Requirement: Queue saturation probe SHALL verify no job loss under concurrent submission
A probe SHALL submit more concurrent async queries than the worker can process and verify all jobs eventually complete.

#### Scenario: Production-history queue saturation
- **WHEN** 5 production-history queries are submitted concurrently (1 worker processing capacity)
- **THEN** all 5 jobs SHALL be enqueued (queue depth momentarily >= 4)
- **THEN** all 5 jobs SHALL eventually reach `status="completed"` or `status="failed"` (no jobs stuck in queued state)
- **THEN** the load report SHALL show peak queue depth for `production-history-query`

#### Scenario: Yield-alert queue saturation
- **WHEN** 5 yield-alert queries are submitted concurrently
- **THEN** all 5 jobs SHALL eventually complete
- **THEN** no job SHALL be silently dropped from the queue

### Requirement: Polling concurrency probe SHALL verify polling endpoint handles concurrent reads
A probe SHALL have multiple clients poll the same job_id simultaneously.

#### Scenario: 10 concurrent polls on same job
- **WHEN** 10 threads poll `GET /api/production-history/job/{job_id}` simultaneously
- **THEN** all 10 SHALL receive consistent status responses (same `status`, same `progress`)
- **THEN** no poll request SHALL return HTTP 500

### Requirement: Job timeout probe SHALL verify timeout behavior
A probe SHALL submit a query designed to exceed the job timeout (1800s) or verify timeout configuration is respected.

#### Scenario: Job timeout detection
- **WHEN** the `PRODUCTION_HISTORY_JOB_TIMEOUT_SECONDS` is temporarily reduced for testing (or a known long-running query is submitted)
- **THEN** the job SHALL transition to `status="failed"` with a timeout-related error
- **THEN** the client polling SHALL detect the failure within one poll interval after timeout

#### Scenario: Job timeout does not corrupt spool
- **WHEN** a job times out mid-execution
- **THEN** no partial spool file SHALL be left registered in Redis
- **THEN** a subsequent query with the same parameters SHALL trigger a fresh job (not serve a corrupt spool)

### Requirement: Retry behavior probe SHALL verify retry limits are respected
A probe SHALL verify that failed jobs are retried according to the configured policy (max 2 retries, intervals [30, 60]s) and do not create retry storms.

#### Scenario: Job retried after transient failure
- **WHEN** a job fails and is auto-retried by RQ
- **THEN** the retry count SHALL not exceed `max=2`
- **THEN** the total job attempts (initial + retries) SHALL be <= 3

#### Scenario: No retry storm under sustained failure
- **WHEN** 10 jobs are submitted and all fail on first attempt
- **THEN** the total job executions SHALL be <= 30 (10 jobs × 3 attempts max)
- **THEN** the queue SHALL drain completely within `10 × (1800 + 30 + 60)` seconds worst case

### Requirement: Spool hit bypass probe SHALL verify cache deduplication
A probe SHALL submit the same query twice and verify the second request gets a synchronous spool hit.

#### Scenario: Duplicate query returns spool hit
- **WHEN** a production-history query is submitted and completes (spool written)
- **THEN** submitting the identical query again SHALL return HTTP 200 (not 202)
- **THEN** the response SHALL contain the same `dataset_id` as the first query

#### Scenario: Concurrent duplicate queries
- **WHEN** 5 identical production-history queries are submitted simultaneously
- **THEN** at most 1 SHALL trigger an actual RQ job
- **THEN** the remaining 4 SHALL either return spool hit (200) or share the same job_id (202 with identical job)

### Requirement: RQ queue depth SHALL be monitored during all stress tests
The `LoadCollector` SHALL sample per-queue RQ depth from the admin endpoint during stress test execution.

#### Scenario: Queue depth recorded for 5 queues
- **WHEN** `LoadCollector` polls the admin RQ status endpoint
- **THEN** it SHALL record queue depth for: `trace-events`, `reject-query`, `msd-analysis`, `production-history-query`, `yield-alert-query`
- **THEN** `LoadSummary` SHALL include `peak_queue_depth` per queue

#### Scenario: Queue depth threshold assertion
- **WHEN** `peak_queue_depth` for any queue exceeds a configurable threshold (`STRESS_MAX_QUEUE_DEPTH`, default 20)
- **THEN** the load report SHALL flag it as a warning
- **THEN** the warning SHALL include the queue name and peak depth

### Requirement: Async data integrity SHALL be verified end-to-end
Each async job probe SHALL verify that the data retrieved after the polling lifecycle matches the expected row count.

#### Scenario: Production-history async integrity
- **WHEN** a production-history query completes via the async path (202 → polling → spool hit)
- **THEN** the three-point row count verification (COUNT baseline, total_rows, pagination sum) SHALL pass

#### Scenario: Yield-alert async integrity
- **WHEN** a yield-alert query completes via the async path
- **THEN** the three-point row count verification SHALL pass
