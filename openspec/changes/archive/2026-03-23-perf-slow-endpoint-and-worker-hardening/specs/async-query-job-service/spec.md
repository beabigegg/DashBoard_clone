## MODIFIED Requirements

### Requirement: enqueue_job SHALL support automatic retry on failure
The `enqueue_job()` function SHALL accept an optional `retry` parameter and pass it to `queue.enqueue()`.

#### Scenario: Default retry enabled
- **WHEN** `enqueue_job()` is called without explicit `retry` parameter
- **THEN** the job SHALL be enqueued with `retry=Retry(max=2, interval=[30, 60])`
- **THEN** transient failures (e.g., DB connection timeout) SHALL trigger automatic re-execution

#### Scenario: Retry disabled explicitly
- **WHEN** `enqueue_job(..., retry=None)` is called
- **THEN** the job SHALL be enqueued without retry (original behavior)

#### Scenario: Custom retry configuration
- **WHEN** `enqueue_job(..., retry=Retry(max=1, interval=10))` is called
- **THEN** the job SHALL use the provided retry configuration

### Requirement: Default job timeout SHALL be reduced to 600 seconds
The `ASYNC_JOB_DEFAULT_TIMEOUT_SECONDS` SHALL default to 600 (was 1800).

#### Scenario: Default timeout
- **WHEN** `enqueue_job()` is called without explicit `job_timeout`
- **THEN** the job SHALL use 600s timeout (configurable via `ASYNC_JOB_TIMEOUT_SECONDS` env var)

### Requirement: Failed job completion SHALL record metrics
The `complete_job()` function SHALL emit a warning log and increment a metrics counter when a job fails.

#### Scenario: Job failure recorded
- **WHEN** `complete_job(prefix, job_id, error="DB timeout")` is called
- **THEN** a WARNING log SHALL be emitted with prefix, job_id, and error message
- **THEN** the failed job counter SHALL be incremented (queryable via admin metrics)
