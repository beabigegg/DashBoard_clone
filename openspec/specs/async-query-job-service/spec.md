### Requirement: Shared async job service SHALL provide job enqueue capability
The `async_query_job_service` module SHALL provide a generic `enqueue_job()` function that enqueues a callable to a named RQ queue with configurable timeout and TTL.

#### Scenario: Successful enqueue
- **WHEN** `enqueue_job(queue_name="reject-query", worker_fn=fn, job_id="reject-abc123", kwargs={...}, job_timeout=1800, result_ttl=3600)` is called
- **THEN** the function SHALL enqueue `fn` to the `reject-query` RQ queue
- **THEN** the function SHALL write initial job metadata to Redis HSET at key `{prefix}:job:{job_id}:meta`
- **THEN** the metadata SHALL include `status=queued`, `created_at`, `queue_name`
- **THEN** the function SHALL return `(job_id, None)` on success

#### Scenario: RQ unavailable
- **WHEN** `enqueue_job()` is called but RQ is not installed or Redis is unreachable
- **THEN** the function SHALL return `(None, "async queue unavailable")`
- **THEN** no exception SHALL be raised

#### Scenario: Enqueue failure
- **WHEN** `enqueue_job()` is called but the RQ enqueue operation fails
- **THEN** the function SHALL return `(None, "<error message>")`
- **THEN** the job metadata SHALL be updated with `status=failed` and `error` field

### Requirement: Shared async job service SHALL provide job status query
The module SHALL provide `get_job_status(prefix, job_id)` that reads job metadata from Redis.

#### Scenario: Job exists and is running
- **WHEN** `get_job_status("reject", "abc123")` is called and the job is in progress
- **THEN** the function SHALL return a dict with `job_id`, `status=running`, `progress`, `created_at`, `elapsed_seconds`

#### Scenario: Job completed
- **WHEN** `get_job_status("reject", "abc123")` is called and the job has finished
- **THEN** the returned dict SHALL include `status=completed`, `query_id`, `completed_at`, `elapsed_seconds`

#### Scenario: Job not found
- **WHEN** `get_job_status("reject", "nonexistent")` is called
- **THEN** the function SHALL return `None`

### Requirement: Shared async job service SHALL provide progress update
The module SHALL provide `update_job_progress(prefix, job_id, **fields)` that updates Redis HSET fields for a running job.

#### Scenario: Progress update during execution
- **WHEN** `update_job_progress("reject", "abc123", status="running", progress="3/10", pct=30)` is called
- **THEN** the Redis HSET at `{prefix}:job:{job_id}:meta` SHALL be updated with the provided fields

### Requirement: Shared async job service SHALL provide job completion marking
The module SHALL provide `complete_job(prefix, job_id, query_id=None, error=None)` that marks a job as completed or failed.

#### Scenario: Successful completion
- **WHEN** `complete_job("reject", "abc123", query_id="deadbeef12345678")` is called
- **THEN** the job metadata SHALL be updated with `status=completed`, `query_id=deadbeef12345678`, `completed_at`

#### Scenario: Failed completion
- **WHEN** `complete_job("reject", "abc123", error="Oracle timeout")` is called
- **THEN** the job metadata SHALL be updated with `status=failed`, `error="Oracle timeout"`, `completed_at`

### Requirement: Shared async job service SHALL provide RQ health check
The module SHALL provide `is_async_available()` that checks RQ installation, Redis connectivity, and worker existence with a 60-second TTL cache.

#### Scenario: All checks pass
- **WHEN** RQ is installed, Redis is reachable, and at least one RQ worker is registered
- **THEN** `is_async_available()` SHALL return `True`

#### Scenario: No workers registered
- **WHEN** RQ is installed and Redis is reachable but no RQ workers are registered
- **THEN** `is_async_available()` SHALL return `False`

#### Scenario: Cached result within TTL
- **WHEN** `is_async_available()` was called 30 seconds ago and returned `True`
- **THEN** the second call SHALL return `True` without performing any checks

### Requirement: Reject query job worker SHALL execute queries in RQ process
The `reject_query_job_service` module SHALL provide `execute_reject_query_job(job_id, mode, params)` as the RQ worker entry point.

#### Scenario: Successful date_range query execution
- **WHEN** `execute_reject_query_job("reject-abc123", "date_range", {"start_date": "2025-01-01", "end_date": "2025-03-31", ...})` runs in the RQ worker
- **THEN** it SHALL execute the same query logic as `execute_primary_query()` (batch engine path)
- **THEN** it SHALL update job progress after each chunk completion via `update_job_progress()`
- **THEN** it SHALL store the result in the spool via `register_spool_file()`
- **THEN** it SHALL call `complete_job()` with the resulting `query_id`

#### Scenario: Query execution failure
- **WHEN** the query execution raises an exception in the RQ worker
- **THEN** the worker SHALL call `complete_job()` with the error message
- **THEN** the job metadata SHALL show `status=failed`

### Requirement: Reject query job service SHALL provide async decision function
The module SHALL provide `should_use_async(mode, start_date, end_date)` that determines whether a query should use the async path.

#### Scenario: Long date range with async available
- **WHEN** `mode="date_range"` and `end_date - start_date > REJECT_ASYNC_DAY_THRESHOLD` (default 10) and `is_async_available()` returns `True`
- **THEN** `should_use_async()` SHALL return `True`

#### Scenario: Short date range
- **WHEN** `mode="date_range"` and `end_date - start_date <= 10`
- **THEN** `should_use_async()` SHALL return `False`

#### Scenario: Container mode
- **WHEN** `mode="container"`
- **THEN** `should_use_async()` SHALL return `False`

#### Scenario: Async unavailable
- **WHEN** date range is long but `is_async_available()` returns `False`
- **THEN** `should_use_async()` SHALL return `False` (graceful fallback to sync)

### Requirement: RQ worker process SHALL be configured for reject-query queue
The deployment scripts SHALL start a dedicated RQ worker process for the `reject-query` queue, independent of the trace-events worker.

#### Scenario: Worker startup
- **WHEN** `RQ_REJECT_WORKER_ENABLED=true` (default)
- **THEN** `start_server.sh` SHALL start a dedicated RQ worker process listening on the `reject-query` queue

#### Scenario: Worker disabled
- **WHEN** `RQ_REJECT_WORKER_ENABLED=false`
- **THEN** no reject-query RQ worker SHALL be started
- **THEN** `should_use_async()` SHALL return `False` due to `is_async_available()` finding no workers

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

### Requirement: Async job service SHALL support multi-stage progress reporting
The shared async query job service SHALL support reporting progress across multiple pipeline stages within a single job.

#### Scenario: Multi-stage progress update
- **WHEN** an RQ job has multiple stages (e.g., seed_detection, lineage, events, aggregation)
- **THEN** `update_job_progress()` SHALL accept a `stage` parameter
- **THEN** the progress metadata in Redis SHALL include `{ "status": "running", "stage": "lineage", "progress": "60%", "completed_stages": ["seed_detection"] }`

#### Scenario: Frontend reads stage progress
- **WHEN** `GET /api/trace/job/<job_id>` is called for a multi-stage job
- **THEN** the response SHALL include `stage` and `completed_stages` fields
- **THEN** the frontend SHALL display the current stage name and overall progress

### Requirement: Async job service SHALL support warmup job enqueueing
The async job service SHALL support enqueueing warmup jobs with lower priority than user-initiated queries.

#### Scenario: Warmup job enqueue
- **WHEN** the warmup scheduler enqueues a warmup job
- **THEN** the job SHALL be enqueued to the designated queue
- **THEN** user-initiated query jobs on the same queue SHALL execute before warmup jobs when both are pending

## Delta: phase4-semantic-ux-classification

### ADDED Requirements

### Requirement: Async query job service SHALL serve as the Type B miss re-dispatch entry point
The async query job service SHALL be the designated re-dispatch mechanism for Type B domains (`reject-history`, `material-trace`, `MSD`) when a view miss (HTTP 410) occurs. The client SHALL use this service to enqueue a new primary query job after receiving a 410.

This service SHALL NOT be invoked automatically by view endpoints. The client is responsible for calling the appropriate domain query endpoint (which internally uses this service) after receiving a 410.

#### Scenario: Type B domain dispatches async job after view miss
- **WHEN** a Type B domain's view endpoint returns HTTP 410 `cache_expired`
- **THEN** the client SHALL POST to the domain's query endpoint with original query parameters
- **THEN** the domain query route SHALL call `should_use_async()` to determine the execution path
- **THEN** if `should_use_async()` returns `True`, the route SHALL call `enqueue_job()` and return HTTP 202 with `{ job_id }`
- **THEN** the client SHALL use `get_job_status(job_id)` to poll until completion

#### Scenario: Job completion provides query_id for view load
- **WHEN** an async job completes successfully
- **THEN** the job result SHALL include the `query_id` of the completed query
- **THEN** the client SHALL use this `query_id` to request the view endpoint
- **THEN** the view endpoint SHALL return the computed result from the spool

### Requirement: Async query job service supports production-history consumer
The `async_query_job_service` SHALL be used by `production_history_job_service` as a consumer without any code changes to the core module. The `enqueue_job` function already accepts arbitrary `queue_name`, `worker_fn`, and `kwargs`.

#### Scenario: Production history job enqueues via shared service
- **WHEN** `production_history_job_service.enqueue_production_history_query()` is called
- **THEN** it SHALL delegate to `async_query_job_service.enqueue_job()` with `queue_name="production-history-query"`

### Requirement: Async query job service supports yield-alert consumer
The `async_query_job_service` SHALL be used by `yield_alert_job_service` as a consumer without any code changes to the core module.

#### Scenario: Yield alert job enqueues via shared service
- **WHEN** `yield_alert_job_service.enqueue_yield_alert_query()` is called
- **THEN** it SHALL delegate to `async_query_job_service.enqueue_job()` with `queue_name="yield-alert-query"`

### Requirement: RQ monitor includes all active queues
The `rq_monitor_service` `_QUEUE_NAMES` list SHALL include all 5 active queue names: `trace-events`, `reject-query`, `msd-analysis`, `production-history-query`, `yield-alert-query`. The existing list is missing `msd-analysis` — this change SHALL fix that omission alongside adding the two new queues.

#### Scenario: All queues appear in monitored queue list
- **WHEN** the RQ monitor scans active queues
- **THEN** `trace-events`, `reject-query`, `msd-analysis`, `production-history-query`, and `yield-alert-query` SHALL all be included in the monitored set

#### Scenario: Admin dashboard displays new workers and queues
- **WHEN** the admin dashboard WorkerTab loads RQ status
- **THEN** the new workers and queues SHALL appear in the Workers table and Queue list (WorkerTab renders dynamically from API data, no frontend code change needed)
